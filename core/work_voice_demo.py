"""Opt-in, owner-scoped incoming test calls; never a PSTN dialling endpoint."""
import re
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from requests.exceptions import RequestException
from twilio.base.exceptions import TwilioException
from twilio.http.http_client import TwilioHttpClient
from twilio.request_validator import RequestValidator
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse

from .models import CallLog, Store, WorkDevice, WorkDeviceEvent
from .store_access import operator_memberships
from .voice_routing import eligible_devices
from .work_device_views import PersonalStoreLookupInput, WorkLoginThrottle


def _public_base():
    # Do not accept an arbitrary callback host from either the browser or config.
    base = settings.TWILIO_WEBHOOK_PUBLIC_BASE_URL.rstrip("/")
    return base if base in ("https://api.roomink.net", "https://api-staging.roomink.net") else ""


def _ready():
    return bool(settings.WORK_VOICE_DEMO_ENABLED and _public_base()
                and str(settings.WORK_VOICE_DEMO_STORE_ID).isdigit()
                and int(settings.WORK_VOICE_DEMO_STORE_ID) > 0
                and settings.TWILIO_WORK_ACCOUNT_SID and settings.TWILIO_WORK_AUTH_TOKEN
                and settings.TWILIO_VOICE_API_KEY_SID and settings.TWILIO_VOICE_API_KEY_SECRET
                and settings.TWILIO_VOICE_PUSH_CREDENTIAL_SID
                and re.fullmatch(r"\+[1-9][0-9]{7,14}", settings.WORK_VOICE_DEMO_FROM_NUMBER))


def _operator(request, data):
    if not _ready():
        raise PermissionDenied("テスト着信は現在利用できません。")
    if data["username"] not in settings.WORK_VOICE_DEMO_USERNAMES:
        raise PermissionDenied("このアカウントではテスト着信を利用できません。")
    user = authenticate(request, username=data["username"], password=data["password"])
    if not user or not user.is_active:
        raise AuthenticationFailed("ユーザー名またはパスワードが正しくありません。")
    if not operator_memberships(user).filter(
        store_id=settings.WORK_VOICE_DEMO_STORE_ID, role__in=("manager", "staff")
    ).exists():
        raise PermissionDenied("検証店舗の利用権限がありません。")
    return user


def _devices(user):
    return [d for d in eligible_devices(int(settings.WORK_VOICE_DEMO_STORE_ID))
            if d.kind == WorkDevice.Kind.PERSONAL and d.owner_id == user.pk]


class DemoCallInput(PersonalStoreLookupInput):
    device_id = serializers.UUIDField()


class DemoDevicesView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [WorkLoginThrottle]

    @extend_schema(request=PersonalStoreLookupInput, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        data = PersonalStoreLookupInput(data=request.data)
        data.is_valid(raise_exception=True)
        user = _operator(request, data.validated_data)
        return Response({"devices": [{"id": str(d.pk), "label": d.label} for d in _devices(user)]},
                        headers={"Cache-Control": "no-store"})


class DemoCallView(DemoDevicesView):
    @extend_schema(request=DemoCallInput, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        data = DemoCallInput(data=request.data)
        data.is_valid(raise_exception=True)
        user = _operator(request, data.validated_data)
        # Store lock + persisted attempts enforce limits across web workers/dynos.
        with transaction.atomic():
            store = Store.objects.select_for_update().get(pk=settings.WORK_VOICE_DEMO_STORE_ID)
            device = next((d for d in _devices(user) if d.pk == data.validated_data["device_id"]), None)
            if device is None:
                raise PermissionDenied("自分の有効な受電端末を選んでください。")
            attempts = WorkDeviceEvent.objects.filter(store=store, action="demo_call_requested")
            now = timezone.now()
            if (attempts.filter(created_at__gte=now - timedelta(seconds=60)).exists()
                    or attempts.filter(created_at__gte=now - timedelta(hours=24)).count() >= 20):
                return Response({"detail": "回数制限に達しました。時間をおいてお試しください。"}, status=429)
            WorkDeviceEvent.objects.create(store=store, actor=user, device=device, action="demo_call_requested")
            request_id = uuid.uuid4()
            call = CallLog.objects.create(store=store, contact_id="work-demo:" + request_id.hex,
                                          from_phone="テスト着信", to_phone="")
        audio = VoiceResponse()
        audio.say("Roomink Workのテスト着信です。この音声が聞こえたら着信と応答の確認は成功です。", language="ja-JP")
        audio.pause(length=2)
        audio.say("テストを終了します。", language="ja-JP")
        audio.hangup()
        try:
            Client(settings.TWILIO_WORK_ACCOUNT_SID, settings.TWILIO_WORK_AUTH_TOKEN,
                   http_client=TwilioHttpClient(timeout=10)).calls.create(
                to="client:roomink_work_" + device.pk.hex,
                from_=settings.WORK_VOICE_DEMO_FROM_NUMBER,
                twiml=str(audio), timeout=25, time_limit=30,
                status_callback=_public_base() + "/api/work/demo/status/?request=" + request_id.hex,
                status_callback_event=["initiated", "ringing", "answered", "completed"],
                status_callback_method="POST",
            )
        except TwilioException:
            # Failed attempts still count; a timeout might already have queued a call.
            CallLog.objects.filter(pk=call.pk, status=CallLog.Status.NEW).update(status=CallLog.Status.MISSED)
            return Response({"detail": "テスト着信を送れませんでした。時間をおいてお試しください。"}, status=502)
        except RequestException:
            # Delivery is unknown after a network timeout. Leave the row open so
            # an authenticated provider callback can record its actual outcome.
            return Response({"detail": "送信結果を確認できません。再送せず、着信と履歴を確認してください。"}, status=502)
        return Response({"detail": "テスト着信を送りました。iPhoneで応答してください。"}, status=202,
                        headers={"Cache-Control": "no-store"})


@csrf_exempt
@require_POST
def status_callback(request):
    if (not _ready() or request.POST.get("AccountSid") != settings.TWILIO_WORK_ACCOUNT_SID
            or not RequestValidator(settings.TWILIO_WORK_AUTH_TOKEN).validate(
                _public_base() + request.get_full_path(), request.POST,
                request.headers.get("X-Twilio-Signature", ""))):
        return HttpResponse(status=403)
    request_id = request.GET.get("request", "")
    if not re.fullmatch(r"[0-9a-f]{32}", request_id):
        return HttpResponse(status=400)
    with transaction.atomic():
        call = CallLog.objects.select_for_update().filter(
            store_id=settings.WORK_VOICE_DEMO_STORE_ID, contact_id="work-demo:" + request_id).first()
        if call and call.status not in (CallLog.Status.DONE, CallLog.Status.MISSED):
            state = request.POST.get("CallStatus")
            if state == "in-progress":
                call.status = CallLog.Status.IN_PROGRESS
            elif state == "completed":
                call.status = CallLog.Status.DONE
            elif state in ("busy", "failed", "no-answer", "canceled"):
                call.status = CallLog.Status.MISSED
            duration = request.POST.get("CallDuration", "0")
            if duration.isdigit():
                call.duration_seconds = min(int(duration), 30)
            call.save(update_fields=["status", "duration_seconds", "updated_at"])
    return HttpResponse("ok")
