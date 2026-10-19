"""Store-selected Work receiving; Groundwire remains the default escape path."""
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Store, VoiceRouteEvent, WorkDevice
from .operation_group_views import operation_group_for_request, scoped_stores
from .work_device_views import entitled_subscriptions


def configured():
    return bool(settings.WORK_VOICE_ROUTING_ENABLED and
                settings.TWILIO_WORK_ACCOUNT_SID == settings.TWILIO_ACCOUNT_SID and
                settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and
                settings.TWILIO_WEBHOOK_PUBLIC_BASE_URL.startswith("https://") and settings.TWILIO_VOICE_API_KEY_SID and
                settings.TWILIO_VOICE_API_KEY_SECRET and settings.TWILIO_VOICE_PUSH_CREDENTIAL_SID)


def eligible_devices(store_id):
    candidates = WorkDevice.objects.filter(
        status="active", platform="ios", store_subscriptions__store_id=store_id,
        store_subscriptions__is_receiving=True, credentials__revoked_at__isnull=True,
        credentials__expires_at__gt=timezone.now(),
    ).distinct().order_by("pk")
    return [d for d in candidates if any(s.store_id == store_id for s in entitled_subscriptions(d, receiving_only=True))]


class VoiceRouteInput(serializers.Serializer):
    store_id = serializers.IntegerField(min_value=1)
    receiver = serializers.ChoiceField(choices=["groundwire", "work"])


class OperationVoiceRouteView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        group_id = operation_group_for_request(request)
        return Response({"work_available": configured(), "stores": list(Store.objects.filter(
            operation_group_id=group_id).order_by("name", "pk").values("id", "name", "voice_receiver"))})

    @extend_schema(request=VoiceRouteInput, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        data = VoiceRouteInput(data=request.data)
        data.is_valid(raise_exception=True)
        group_id = operation_group_for_request(request)
        with transaction.atomic():
            stores = scoped_stores(group_id, [data.validated_data["store_id"]], lock=True)
            store = stores[0]
            receiver = data.validated_data["receiver"]
            # Switching back is always permitted even if Work configuration broke.
            if receiver == "work":
                if not configured():
                    raise ValidationError("Workへの切り替えはまだ利用できません。")
                devices = eligible_devices(store.pk)
                if not devices or len(devices) > 10:
                    raise ValidationError("受信ONの有効なWork端末を1〜10台用意してください。")
            previous = store.voice_receiver
            if previous != receiver:
                store.voice_receiver = receiver
                store.save(update_fields=["voice_receiver"])
                VoiceRouteEvent.objects.create(store=store, actor=request.user, previous=previous, selected=receiver)
        return Response({"id": store.pk, "voice_receiver": store.voice_receiver})
