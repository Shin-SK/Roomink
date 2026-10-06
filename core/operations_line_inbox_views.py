"""Read-only intake for the Roomink operations LINE Official Account.

The endpoint deliberately has no reply or push-message capability.  Its only
responsibility is to capture an incoming message (and available media) so the
operator can ask Codex to inspect it later.
"""

import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta, timezone as datetime_timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import OperationsLineInboxAttachment, OperationsLineInboxMessage


logger = logging.getLogger(__name__)
MEDIA_TYPES = {"image", "video", "audio", "file"}


def _purge_expired():
    OperationsLineInboxMessage.objects.filter(expires_at__lte=timezone.now()).delete()


def _line_signature_is_valid(request):
    secret = settings.OPERATIONS_LINE_INBOX_CHANNEL_SECRET
    if not secret:
        return False
    expected = base64.b64encode(
        hmac.new(secret.encode("utf-8"), request.body, hashlib.sha256).digest()
    ).decode("utf-8")
    return hmac.compare_digest(request.headers.get("X-Line-Signature", ""), expected)


def _read_token_is_valid(request):
    token = settings.OPERATIONS_LINE_INBOX_READ_TOKEN
    header = request.headers.get("Authorization", "")
    return bool(token and hmac.compare_digest(header, f"Bearer {token}"))


def _received_at(event):
    timestamp_ms = event.get("timestamp")
    if isinstance(timestamp_ms, (int, float)):
        return datetime.fromtimestamp(timestamp_ms / 1000, tz=datetime_timezone.utc)
    return timezone.now()


def _attachment_filename(message):
    filename = (message.get("fileName") or "").strip()
    return filename[:255]


def _fetch_attachment(attachment):
    """Fetch once from LINE; video/audio can initially answer 202 while preparing."""
    attachment.fetch_attempts += 1
    attachment.last_attempted_at = timezone.now()
    token = settings.OPERATIONS_LINE_INBOX_CHANNEL_ACCESS_TOKEN
    if not token:
        attachment.status = OperationsLineInboxAttachment.Status.FAILED
        attachment.error = "LINE media token is not configured."
        attachment.save(update_fields=["fetch_attempts", "last_attempted_at", "status", "error"])
        return attachment

    request = Request(
        f"https://api-data.line.me/v2/bot/message/{attachment.line_message_id}/content",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    max_bytes = settings.OPERATIONS_LINE_INBOX_MAX_ATTACHMENT_BYTES
    try:
        with urlopen(request, timeout=20) as response:
            declared_size = int(response.headers.get("Content-Length") or 0)
            if declared_size > max_bytes:
                attachment.status = OperationsLineInboxAttachment.Status.TOO_LARGE
                attachment.error = f"Attachment exceeds {max_bytes} bytes."
                attachment.size_bytes = declared_size
            else:
                chunks = []
                actual_size = 0
                while True:
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    actual_size += len(chunk)
                    if actual_size > max_bytes:
                        attachment.status = OperationsLineInboxAttachment.Status.TOO_LARGE
                        attachment.error = f"Attachment exceeds {max_bytes} bytes."
                        attachment.size_bytes = actual_size
                        chunks = []
                        break
                    chunks.append(chunk)
                else:  # pragma: no cover - loop only ends through break
                    pass
                if chunks or actual_size == 0:
                    attachment.content = b"".join(chunks)
                    attachment.content_type = (response.headers.get("Content-Type") or attachment.content_type)[:255]
                    attachment.size_bytes = actual_size
                    attachment.status = OperationsLineInboxAttachment.Status.STORED
                    attachment.error = ""
    except HTTPError as error:
        attachment.status = (
            OperationsLineInboxAttachment.Status.PENDING
            if error.code == 202
            else OperationsLineInboxAttachment.Status.FAILED
        )
        attachment.error = f"LINE media request returned HTTP {error.code}."
    except (URLError, TimeoutError, ValueError):
        logger.warning("Unable to fetch operations LINE attachment", exc_info=True)
        attachment.status = OperationsLineInboxAttachment.Status.FAILED
        attachment.error = "LINE media could not be retrieved."
    attachment.save(update_fields=[
        "fetch_attempts", "last_attempted_at", "content", "content_type", "size_bytes",
        "status", "error",
    ])
    return attachment


def _capture_message(event):
    message = event.get("message") or {}
    message_type = message.get("type") or "other"
    if message_type not in {choice for choice, _ in OperationsLineInboxMessage.MessageType.choices}:
        message_type = OperationsLineInboxMessage.MessageType.OTHER
    source = event.get("source") or {}
    received_at = _received_at(event)
    event_id = str(event.get("webhookEventId") or "")[:100]
    if not event_id:
        return
    expires_at = received_at + timedelta(days=max(1, settings.OPERATIONS_LINE_INBOX_RETENTION_DAYS))
    try:
        with transaction.atomic():
            inbox_message = OperationsLineInboxMessage.objects.create(
                line_event_id=event_id,
                line_message_id=str(message.get("id") or "")[:100],
                source_type=str(source.get("type") or "")[:12],
                source_id=str(source.get("groupId") or source.get("roomId") or source.get("userId") or "")[:100],
                sender_user_id=str(source.get("userId") or "")[:100],
                message_type=message_type,
                text=(message.get("text") or "") if message_type == "text" else "",
                received_at=received_at,
                expires_at=expires_at,
            )
    except IntegrityError:
        return  # LINE redelivery: the original event is already safely persisted.

    if message_type in MEDIA_TYPES and message.get("id"):
        attachment = OperationsLineInboxAttachment.objects.create(
            message=inbox_message,
            line_message_id=str(message["id"])[:100],
            filename=_attachment_filename(message),
            duration_ms=(
                message.get("duration")
                if isinstance(message.get("duration"), int) and message["duration"] >= 0
                else None
            ),
        )
        _fetch_attachment(attachment)


def _process_unsend(event):
    message_id = str((event.get("unsend") or {}).get("messageId") or "")
    if not message_id:
        return
    now = timezone.now()
    for message in OperationsLineInboxMessage.objects.filter(line_message_id=message_id, withdrawn_at__isnull=True):
        message.text = ""
        message.withdrawn_at = now
        message.save(update_fields=["text", "withdrawn_at"])
        message.attachments.update(
            content=None,
            status=OperationsLineInboxAttachment.Status.WITHDRAWN,
            error="Removed because the sender unsent this message.",
        )


@extend_schema(operation_id="operations_line_inbox_webhook", request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def operations_line_inbox_webhook(request):
    if not settings.OPERATIONS_LINE_INBOX_ENABLED:
        return Response({"detail": "Operations LINE inbox is disabled."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    if not _line_signature_is_valid(request):
        return Response({"detail": "Invalid signature."}, status=status.HTTP_403_FORBIDDEN)
    try:
        events = json.loads(request.body.decode("utf-8")).get("events", [])
    except (UnicodeDecodeError, json.JSONDecodeError):
        return Response({"detail": "Invalid payload."}, status=status.HTTP_400_BAD_REQUEST)
    _purge_expired()
    for event in events:
        if event.get("type") == "message":
            _capture_message(event)
        elif event.get("type") == "unsend":
            _process_unsend(event)
    return Response({"ok": True})


def _attachment_data(attachment):
    return {
        "id": attachment.pk,
        "filename": attachment.filename,
        "content_type": attachment.content_type,
        "size_bytes": attachment.size_bytes,
        "duration_ms": attachment.duration_ms,
        "status": attachment.status,
        "error": attachment.error,
        "download_path": f"/api/internal/operations-line-inbox/attachments/{attachment.pk}/",
    }


@extend_schema(operation_id="operations_line_inbox_recent", responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def operations_line_inbox_recent(request):
    if not _read_token_is_valid(request):
        return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)
    _purge_expired()
    try:
        limit = min(max(int(request.query_params.get("limit", 20)), 1), 100)
    except ValueError:
        limit = 20
    messages = OperationsLineInboxMessage.objects.prefetch_related("attachments").all()[:limit]
    return Response({"messages": [{
        "id": message.pk,
        "received_at": message.received_at,
        "source_type": message.source_type,
        "source_id": message.source_id,
        "message_type": message.message_type,
        "text": message.text,
        "withdrawn_at": message.withdrawn_at,
        "attachments": [_attachment_data(item) for item in message.attachments.all()],
    } for message in messages]})


@extend_schema(operation_id="operations_line_inbox_attachment", responses=OpenApiTypes.BINARY)
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def operations_line_inbox_attachment(request, attachment_id):
    if not _read_token_is_valid(request):
        return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)
    _purge_expired()
    try:
        attachment = OperationsLineInboxAttachment.objects.select_related("message").get(pk=attachment_id)
    except OperationsLineInboxAttachment.DoesNotExist:
        return Response({"detail": "Attachment not found."}, status=status.HTTP_404_NOT_FOUND)
    if attachment.status in {OperationsLineInboxAttachment.Status.PENDING, OperationsLineInboxAttachment.Status.FAILED}:
        _fetch_attachment(attachment)
    if attachment.status != OperationsLineInboxAttachment.Status.STORED or attachment.content is None:
        return Response({"detail": attachment.error or "Attachment is not available.", "status": attachment.status}, status=status.HTTP_409_CONFLICT)
    response = HttpResponse(bytes(attachment.content), content_type=attachment.content_type or "application/octet-stream")
    filename = attachment.filename or f"line-attachment-{attachment.pk}"
    filename = filename.replace("\\", "_").replace("\r", "").replace("\n", "").replace('"', "")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
