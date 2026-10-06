import base64
import hashlib
import hmac
import json
from datetime import timedelta
from io import BytesIO
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import OperationsLineInboxAttachment, OperationsLineInboxMessage


INBOX_SETTINGS = {
    "OPERATIONS_LINE_INBOX_ENABLED": True,
    "OPERATIONS_LINE_INBOX_CHANNEL_SECRET": "line-inbox-secret",
    "OPERATIONS_LINE_INBOX_CHANNEL_ACCESS_TOKEN": "line-inbox-access-token",
    "OPERATIONS_LINE_INBOX_READ_TOKEN": "codex-read-token",
    "OPERATIONS_LINE_INBOX_RETENTION_DAYS": 30,
    "OPERATIONS_LINE_INBOX_MAX_ATTACHMENT_BYTES": 1024,
}


class FakeMediaResponse(BytesIO):
    def __init__(self, content, content_type="image/jpeg"):
        super().__init__(content)
        self.headers = {"Content-Type": content_type, "Content-Length": str(len(content))}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


@override_settings(**INBOX_SETTINGS)
class OperationsLineInboxTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def post_event(self, event):
        raw = json.dumps({"events": [event]}, ensure_ascii=False).encode("utf-8")
        signature = base64.b64encode(
            hmac.new(INBOX_SETTINGS["OPERATIONS_LINE_INBOX_CHANNEL_SECRET"].encode(), raw, hashlib.sha256).digest()
        ).decode()
        return self.client.generic(
            "POST",
            "/api/webhook/operations-line-inbox/",
            raw,
            content_type="application/json",
            HTTP_X_LINE_SIGNATURE=signature,
        )

    def text_event(self, event_id="event-1", message_id="message-1"):
        return {
            "type": "message",
            "webhookEventId": event_id,
            "timestamp": int(timezone.now().timestamp() * 1000),
            "source": {"type": "user", "userId": "U-reporter"},
            "message": {"id": message_id, "type": "text", "text": "予約について相談したいです"},
        }

    def test_signed_text_message_is_saved_once_without_replying(self):
        response = self.post_event(self.text_event())
        duplicate = self.post_event(self.text_event())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(OperationsLineInboxMessage.objects.count(), 1)
        saved = OperationsLineInboxMessage.objects.get()
        self.assertEqual(saved.text, "予約について相談したいです")
        self.assertEqual(saved.source_id, "U-reporter")
        self.assertEqual(saved.message_type, "text")

    def test_invalid_signature_is_rejected_without_persistence(self):
        response = self.client.post(
            "/api/webhook/operations-line-inbox/",
            {"events": [self.text_event()]},
            format="json",
            HTTP_X_LINE_SIGNATURE="invalid",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(OperationsLineInboxMessage.objects.exists())

    @patch("core.operations_line_inbox_views.urlopen")
    def test_image_is_fetched_and_available_only_with_read_token(self, urlopen):
        urlopen.return_value = FakeMediaResponse(b"jpeg-binary")
        event = self.text_event(event_id="image-event", message_id="image-message")
        event["message"] = {"id": "image-message", "type": "image"}

        response = self.post_event(event)
        attachment = OperationsLineInboxAttachment.objects.get()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(attachment.status, OperationsLineInboxAttachment.Status.STORED)
        self.assertEqual(attachment.content, b"jpeg-binary")
        denied = self.client.get("/api/internal/operations-line-inbox/recent/")
        allowed = self.client.get(
            "/api/internal/operations-line-inbox/recent/",
            HTTP_AUTHORIZATION="Bearer codex-read-token",
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(allowed.status_code, 200)
        attachment_response = self.client.get(
            f"/api/internal/operations-line-inbox/attachments/{attachment.pk}/",
            HTTP_AUTHORIZATION="Bearer codex-read-token",
        )
        self.assertEqual(attachment_response.status_code, 200)
        self.assertEqual(attachment_response.content, b"jpeg-binary")

    @patch("core.operations_line_inbox_views.urlopen")
    def test_oversized_attachment_is_not_written_to_database(self, urlopen):
        urlopen.return_value = FakeMediaResponse(b"x" * 2048, "video/mp4")
        event = self.text_event(event_id="video-event", message_id="video-message")
        event["message"] = {"id": "video-message", "type": "video", "duration": 1000}

        self.post_event(event)
        attachment = OperationsLineInboxAttachment.objects.get()

        self.assertEqual(attachment.status, OperationsLineInboxAttachment.Status.TOO_LARGE)
        self.assertIsNone(attachment.content)

    def test_unsend_removes_saved_body_and_attachment(self):
        message = OperationsLineInboxMessage.objects.create(
            line_event_id="saved-event",
            line_message_id="unsent-message",
            message_type=OperationsLineInboxMessage.MessageType.TEXT,
            text="取り消す本文",
            received_at=timezone.now(),
            expires_at=timezone.now() + timedelta(days=30),
        )
        attachment = OperationsLineInboxAttachment.objects.create(
            message=message,
            line_message_id="unsent-message",
            content=b"private-file",
            status=OperationsLineInboxAttachment.Status.STORED,
        )
        event = {"type": "unsend", "webhookEventId": "unsend-event", "unsend": {"messageId": "unsent-message"}}

        response = self.post_event(event)
        message.refresh_from_db()
        attachment.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(message.text, "")
        self.assertIsNotNone(message.withdrawn_at)
        self.assertIsNone(attachment.content)
        self.assertEqual(attachment.status, OperationsLineInboxAttachment.Status.WITHDRAWN)

    def test_expired_messages_are_purged_before_reading(self):
        OperationsLineInboxMessage.objects.create(
            line_event_id="expired-event",
            message_type=OperationsLineInboxMessage.MessageType.TEXT,
            received_at=timezone.now() - timedelta(days=31),
            expires_at=timezone.now() - timedelta(seconds=1),
        )

        response = self.client.get(
            "/api/internal/operations-line-inbox/recent/",
            HTTP_AUTHORIZATION="Bearer codex-read-token",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["messages"], [])
        self.assertFalse(OperationsLineInboxMessage.objects.exists())
