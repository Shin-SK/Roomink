"""Single-store staging voice experiment, separate from production BYOC/SIP."""
import re
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import VoiceResponse
from .models import CallLog, Store, WorkDevice
from .work_device_views import entitled_subscriptions

PUBLIC_BASE = "https://api-staging.roomink.net"

def _authorized(request):
    if not settings.WORK_VOICE_TEST_ENABLED or settings.WORK_VOICE_ENV != "staging":
        return False
    if not settings.TWILIO_WORK_AUTH_TOKEN or not settings.TWILIO_WORK_ACCOUNT_SID:
        return False
    if request.POST.get("AccountSid") != settings.TWILIO_WORK_ACCOUNT_SID:
        return False
    return RequestValidator(settings.TWILIO_WORK_AUTH_TOKEN).validate(
        PUBLIC_BASE + request.get_full_path(), request.POST,
        request.headers.get("X-Twilio-Signature", ""),
    )

def _xml(response):
    return HttpResponse(str(response), content_type="text/xml")

@csrf_exempt
@require_POST
def incoming(request):
    if not _authorized(request):
        return HttpResponse(status=403)
    response = VoiceResponse()
    sid = request.POST.get("CallSid", "")
    if (not re.fullmatch(r"CA[0-9a-fA-F]{32}", sid)
            or not settings.WORK_VOICE_TEST_NUMBER
            or request.POST.get("To") != settings.WORK_VOICE_TEST_NUMBER):
        response.reject()
        return _xml(response)
    try:
        store_id = int(settings.WORK_VOICE_TEST_STORE_ID)
        store = Store.objects.get(pk=store_id)
    except (Store.DoesNotExist, ValueError, TypeError, ValidationError):
        response.reject()
        return _xml(response)
    candidates = WorkDevice.objects.filter(
        status=WorkDevice.Status.ACTIVE, platform="ios",
        store_subscriptions__store_id=store_id,
        store_subscriptions__is_receiving=True,
        credentials__revoked_at__isnull=True,
        credentials__expires_at__gt=timezone.now(),
    ).distinct().order_by("pk")
    devices = [device for device in candidates if any(
        sub.store_id == store_id
        for sub in entitled_subscriptions(device, receiving_only=True)
    )]
    # Twilio allows at most ten parallel destinations. Never silently omit staff.
    if not devices or len(devices) > 10:
        response.reject()
        return _xml(response)
    with transaction.atomic():
        Store.objects.select_for_update().get(pk=store.pk)
        trial_calls = CallLog.objects.filter(contact_id__startswith="work-test:", store_id=store_id)
        if not trial_calls.filter(contact_id="work-test:" + sid).exists() and trial_calls.count() >= 5:
            response.reject()
            return _xml(response)
        call, created = CallLog.objects.get_or_create(
            contact_id="work-test:" + sid,
            defaults={"store_id": store_id, "from_phone": request.POST.get("From", "")[:20],
                      "to_phone": settings.WORK_VOICE_TEST_NUMBER},
        )
    if not created and (call.store_id != store_id or call.status in (CallLog.Status.DONE, CallLog.Status.MISSED)):
        response.hangup()
        return _xml(response)
    dial = response.dial(timeout=20, time_limit=120, answer_on_bridge=True,
                         action=PUBLIC_BASE + "/api/work/voice-test/finished/", method="POST")
    for device in devices:
        dial.client("roomink_work_" + device.pk.hex,
                    status_callback=PUBLIC_BASE + "/api/work/voice-test/finished/?parent=" + sid,
                    status_callback_event="answered completed", status_callback_method="POST")
    return _xml(response)

@csrf_exempt
@require_POST
def finished(request):
    if not _authorized(request):
        return HttpResponse(status=403)
    try:
        store_id = int(settings.WORK_VOICE_TEST_STORE_ID)
    except (ValueError, TypeError):
        return HttpResponse(status=403)
    with transaction.atomic():
        call = CallLog.objects.select_for_update().filter(
            contact_id="work-test:" + request.GET.get("parent", request.POST.get("CallSid", "")),
            store_id=store_id,
        ).first()
        if call:
            dial_status = request.POST.get("DialCallStatus")
            call_status = request.POST.get("CallStatus")
            child_callback = bool(request.GET.get("parent"))
            answered = dial_status == "completed" or (child_callback and call_status == "completed")
            if answered:
                call.status = CallLog.Status.DONE
                duration = request.POST.get("DialCallDuration", request.POST.get("CallDuration", "0"))
                if duration.isdigit():
                    call.duration_seconds = max(call.duration_seconds, min(int(duration), 120))
            elif child_callback and call_status == "in-progress" and call.status == CallLog.Status.NEW:
                call.status = CallLog.Status.IN_PROGRESS
            # A losing child being cancelled must not end the shared parent call.
            elif not child_callback and call.status != CallLog.Status.DONE and (dial_status or call_status in ("completed", "failed", "busy", "no-answer", "canceled")):
                call.status = CallLog.Status.DONE if call.status == CallLog.Status.IN_PROGRESS and not dial_status else CallLog.Status.MISSED
            call.save(update_fields=["status", "duration_seconds", "updated_at"])
    response = VoiceResponse()
    response.hangup()
    return _xml(response)
