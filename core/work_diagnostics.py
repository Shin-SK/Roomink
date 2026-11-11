from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from .management.commands.export_voice_replay import replay_case
from .models import CallLog, WorkDiagnosticEvent
from .operation_group_views import operation_group_for_request
from .work_device_views import IsWorkDevice, WorkDeviceAuthentication, entitled_subscriptions


STAGES = [
    "push_received", "callkit_requested", "callkit_reported", "callkit_failed",
    "registering", "registered", "registration_failed", "invite", "accepted",
    "rejected", "cancelled", "connecting", "connected", "reconnecting",
    "ended", "error", "app_state",
]


class Snapshot(serializers.Serializer):
    os = serializers.CharField(max_length=24, required=False)
    app_version = serializers.CharField(max_length=32, required=False)
    model = serializers.CharField(max_length=64, required=False)
    build = serializers.CharField(max_length=32, required=False)
    revision = serializers.RegexField(r"^(?:[0-9a-f]{40}|local|unknown)$", required=False)
    origin = serializers.ChoiceField(choices=["native", "javascript"], required=False)
    network = serializers.ChoiceField(choices=["wifi", "cellular", "other", "unavailable", "unknown"], required=False)
    low_power = serializers.BooleanField(required=False)
    push_token_present = serializers.BooleanField(required=False)
    last_registered_at = serializers.DateTimeField(required=False)
    sequence = serializers.IntegerField(min_value=0, required=False)
    uptime_ms = serializers.IntegerField(min_value=0, required=False)
    app_state = serializers.ChoiceField(choices=["active", "inactive", "background", "unknown"], required=False)
    protected_data = serializers.BooleanField(required=False)
    error_code = serializers.IntegerField(required=False)


class Observation(serializers.Serializer):
    event_id = serializers.UUIDField()
    call_sid = serializers.RegexField(r"^CA[0-9a-fA-F]{32}$", required=False, allow_blank=True)
    stage = serializers.ChoiceField(choices=STAGES)
    observed_at = serializers.DateTimeField()
    snapshot = Snapshot()

    def validate_observed_at(self, value):
        if value > timezone.now() + timedelta(minutes=5) or value < timezone.now() - timedelta(days=7):
            raise serializers.ValidationError("診断の時刻が保存範囲外です。")
        return value


class ObservationBatch(serializers.Serializer):
    events = Observation(many=True, max_length=100, allow_empty=False)


class DiagnosticThrottle(UserRateThrottle):
    rate = "60/minute"
    scope = "work_diagnostics"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": request.work_device.pk}


class DeviceDiagnosticsView(APIView):
    authentication_classes = [WorkDeviceAuthentication]
    permission_classes = [IsWorkDevice]
    throttle_classes = [DiagnosticThrottle]

    @extend_schema(request=ObservationBatch, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        data = ObservationBatch(data=request.data)
        data.is_valid(raise_exception=True)
        device = request.work_device
        if device.status != "active" or not entitled_subscriptions(device):
            return Response({"detail": "有効な受信端末が必要です。"}, status=403)
        events = data.validated_data["events"]
        WorkDiagnosticEvent.objects.filter(
            device=device, observed_at__lt=timezone.now() - timedelta(days=7),
        ).delete()
        # JSONField requires JSON-native values after serializer validation.
        for event in events:
            registered_at = event["snapshot"].get("last_registered_at")
            if registered_at:
                event["snapshot"]["last_registered_at"] = registered_at.isoformat()
        with transaction.atomic():
            WorkDiagnosticEvent.objects.bulk_create(
                [WorkDiagnosticEvent(device=device, **event) for event in events],
                ignore_conflicts=True,
            )
        return Response({"accepted": [str(event["event_id"]) for event in events]})


class OperationDiagnosticsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        group_id = operation_group_for_request(request)
        calls = CallLog.objects.filter(store__operation_group_id=group_id)
        call_id = request.query_params.get("call_id")
        if not call_id:
            return Response({"calls": list(calls.order_by("-created_at").values(
                "id", "store_id", "store__name", "created_at", "status",
            )[:50])})
        call = get_object_or_404(calls, pk=call_id if call_id.isdecimal() else 0)
        server_events = list(call.diagnostic_events.order_by("received_at", "id")[:500])
        sids = {call.contact_id}
        if call.contact_id.startswith("work-test:"):
            sids.add(call.contact_id.removeprefix("work-test:"))
        for event in server_events:
            sids.add(event.call_sid)
            child = event.details.get("DialCallSid")
            if child:
                sids.add(child)
        targets = list(dict.fromkeys(
            event.details["DeviceId"] for event in server_events if event.details.get("DeviceId")
        ))
        devices = WorkDiagnosticEvent.objects.filter(
            Q(device_id__in=targets) |
            Q(device__store_subscriptions__store_id=call.store_id),
        ).filter(
            Q(call_sid__in=sids) |
            Q(call_sid="", observed_at__gte=call.created_at - timedelta(minutes=5),
              observed_at__lte=call.created_at + timedelta(minutes=5))
        ).distinct().order_by("observed_at", "received_at", "id")[:500]
        observations = [{
            "device": str(event.device_id), "stage": event.stage,
            "at_ms": (event.observed_at - call.created_at) // timedelta(milliseconds=1),
            "snapshot": event.snapshot,
            "correlation": "call" if event.call_sid else "nearby",
            "received_at": event.received_at,
        } for event in devices]
        replay = replay_case(call, server_events)
        device_aliases = {target: f"device-{index + 1}" for index, target in enumerate(targets)}
        replay["device_events"] = []
        for event in observations:
            alias = device_aliases.setdefault(event["device"], f"device-{len(device_aliases) + 1}")
            replay["device_events"].append({
                "device": alias, "stage": event["stage"], "at_ms": event["at_ms"],
                "snapshot": event["snapshot"],
            })
        return Response({
            "call_id": call.pk, "server": replay["events"], "devices": observations,
            "device_observation": "observed" if any(
                event["correlation"] == "call" for event in observations
            ) else "unobserved",
            "targets": [{
                "device": device_aliases[target],
                "last_stage": next((
                    event["stage"] for event in reversed(observations)
                    if event["device"] == target and event["correlation"] == "call"
                ), None),
                "observation": "observed" if any(
                    event["device"] == target and event["correlation"] == "call"
                    for event in observations
                ) else "unobserved",
            } for target in targets],
            "replay": replay,
        })
