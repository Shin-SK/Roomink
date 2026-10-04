import base64
import hashlib
import hmac
import json

from django.conf import settings
from django.db import IntegrityError
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import OperationsCase, OperationsCaseMessage, OperationsLineContact
from .services.operations_intake import send_line_reply
from .services.support_assistant import redact_sensitive_text


def _valid_signature(request):
    secret = settings.OPERATIONS_LINE_CHANNEL_SECRET
    if not secret:
        return False
    expected = base64.b64encode(
        hmac.new(secret.encode("utf-8"), request.body, hashlib.sha256).digest()
    ).decode("utf-8")
    return hmac.compare_digest(request.headers.get("X-Line-Signature", ""), expected)


def _active_case_for(contact):
    return (
        OperationsCase.objects.filter(
            reporter=contact,
            status=OperationsCase.Status.TRIAGE,
        )
        .order_by("-updated_at")
        .first()
    )


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def operations_line_webhook(request):
    """Roomink運営LINE専用。店舗・キャスト用の既存webhookには混ぜない。"""
    if not settings.OPERATIONS_LINE_INTAKE_ENABLED:
        return Response({"detail": "Operations LINE intake is disabled"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    if not _valid_signature(request):
        return Response({"detail": "Invalid signature"}, status=status.HTTP_403_FORBIDDEN)

    try:
        events = json.loads(request.body.decode("utf-8")).get("events", [])
    except (UnicodeDecodeError, json.JSONDecodeError):
        return Response({"detail": "Invalid payload"}, status=status.HTTP_400_BAD_REQUEST)

    for event in events:
        source = event.get("source") or {}
        # 運営LINEは承認済みの個人トークだけ。グループに店舗LINEを混在させない。
        if source.get("type") != "user" or not source.get("userId"):
            continue
        line_user_id = source["userId"]
        event_type = event.get("type")

        if event_type == "follow":
            OperationsLineContact.objects.get_or_create(line_user_id=line_user_id)
            continue

        if event_type == "unsend":
            message_id = str((event.get("unsend") or {}).get("messageId") or "")
            if message_id:
                OperationsCaseMessage.objects.filter(
                    line_message_id=message_id,
                    withdrawn_at__isnull=True,
                ).update(content="", withdrawn_at=timezone.now())
            continue

        if event_type != "message":
            continue
        message = event.get("message") or {}
        if message.get("type") != "text":
            continue
        contact = OperationsLineContact.objects.filter(
            line_user_id=line_user_id,
            status=OperationsLineContact.Status.ACTIVE,
            store__isnull=False,
        ).select_related("store").first()
        if contact is None:
            OperationsLineContact.objects.get_or_create(line_user_id=line_user_id)
            continue

        event_id = str(event.get("webhookEventId") or "")
        if event_id and OperationsCaseMessage.objects.filter(line_event_id=event_id).exists():
            continue
        content = redact_sensitive_text(message.get("text") or "")
        if not content:
            continue
        case = _active_case_for(contact)
        if case is None:
            case = OperationsCase.objects.create(store=contact.store, reporter=contact)
        try:
            OperationsCaseMessage.objects.create(
                case=case,
                role=OperationsCaseMessage.Role.REPORTER,
                content=content,
                line_event_id=event_id or None,
                line_message_id=str(message.get("id") or ""),
            )
        except IntegrityError:
            continue
        contact.last_seen_at = timezone.now()
        contact.save(update_fields=["last_seen_at", "updated_at"])
        case.triage_requested_at = timezone.now()
        case.save(update_fields=["triage_requested_at", "updated_at"])
        send_line_reply(
            event.get("replyToken", ""),
            "内容を確認しています。必要なことだけ追加でお伺いします。",
        )

    return Response({"ok": True})
