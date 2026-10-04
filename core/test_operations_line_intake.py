import base64
import hashlib
import hmac
import json
from datetime import timedelta
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .models import OperationsCase, OperationsCaseMessage, OperationsLineContact, Store


@override_settings(
    OPERATIONS_LINE_INTAKE_ENABLED=True,
    OPERATIONS_LINE_CHANNEL_SECRET="operations-line-test-secret",
    OPERATIONS_LINE_CHANNEL_ACCESS_TOKEN="",
)
class OperationsLineIntakeWebhookTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.store = Store.objects.create(name="運営LINE検証店", slug="ops-line-test")
        self.contact = OperationsLineContact.objects.create(
            store=self.store,
            line_user_id="U-approved-contact",
            display_name="店舗運営者",
            status=OperationsLineContact.Status.ACTIVE,
        )

    def _post(self, events, valid=True):
        body = json.dumps({"events": events}, ensure_ascii=False).encode("utf-8")
        digest = hmac.new(
            b"operations-line-test-secret", body, hashlib.sha256,
        ).digest()
        signature = base64.b64encode(digest).decode("utf-8") if valid else "invalid"
        return self.client.post(
            "/api/webhook/operations-line/",
            data=body,
            content_type="application/json",
            HTTP_X_LINE_SIGNATURE=signature,
        )

    def _message_event(self, text="設定画面で保存を押すとエラーになります", event_id="evt-1", message_id="msg-1"):
        return {
            "type": "message",
            "webhookEventId": event_id,
            "source": {"type": "user", "userId": self.contact.line_user_id},
            "message": {"type": "text", "id": message_id, "text": text},
        }

    def test_only_allowlisted_contact_creates_a_store_scoped_case(self):
        response = self._post([self._message_event()])

        self.assertEqual(response.status_code, 200)
        case = OperationsCase.objects.get()
        self.assertEqual(case.store, self.store)
        self.assertEqual(case.reporter, self.contact)
        self.assertEqual(case.status, OperationsCase.Status.TRIAGE)
        self.assertIsNotNone(case.triage_requested_at)
        message = case.messages.get(role=OperationsCaseMessage.Role.REPORTER)
        self.assertEqual(message.line_event_id, "evt-1")

    def test_same_line_event_is_idempotent(self):
        event = self._message_event()
        self._post([event])
        self._post([event])

        self.assertEqual(OperationsCase.objects.count(), 1)
        self.assertEqual(OperationsCaseMessage.objects.count(), 1)

    def test_unknown_contact_is_pending_and_cannot_create_case(self):
        event = self._message_event()
        event["source"]["userId"] = "U-not-allowed"
        self._post([event])

        self.assertEqual(OperationsCase.objects.count(), 0)
        contact = OperationsLineContact.objects.get(line_user_id="U-not-allowed")
        self.assertEqual(contact.status, OperationsLineContact.Status.PENDING)
        self.assertIsNone(contact.store)

    def test_invalid_signature_is_rejected_before_persistence(self):
        response = self._post([self._message_event()], valid=False)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(OperationsCase.objects.count(), 0)

    def test_unsend_purges_the_saved_message_body(self):
        self._post([self._message_event(message_id="msg-to-unsend")])
        response = self._post([{
            "type": "unsend",
            "source": {"type": "user", "userId": self.contact.line_user_id},
            "unsend": {"messageId": "msg-to-unsend"},
        }])

        self.assertEqual(response.status_code, 200)
        message = OperationsCaseMessage.objects.get()
        self.assertEqual(message.content, "")
        self.assertIsNotNone(message.withdrawn_at)

    @patch("core.services.operations_intake.sync_case_to_notion")
    @patch("core.services.operations_intake.create_slack_case_thread")
    @patch("core.services.operations_intake.send_line_push")
    @patch("core.services.operations_intake.triage_case")
    def test_worker_turns_ready_case_into_a_single_slack_and_notion_case(
        self, triage, send_line, slack, notion,
    ):
        self._post([self._message_event(text="予約一覧を見やすく修正してほしいです")])
        case = OperationsCase.objects.get()
        case.triage_requested_at = timezone.now() - timedelta(seconds=6)
        case.save(update_fields=["triage_requested_at", "updated_at"])
        triage.return_value = {
            "category": OperationsCase.Category.CHANGE,
            "summary": "予約一覧の視認性を改善したい要望",
            "missing_information": [],
            "line_reply": "内容を整理してRoomink運営へ共有しました。",
            "ready_for_review": True,
        }

        call_command("process_operations_line_intake")

        case.refresh_from_db()
        self.assertEqual(case.status, OperationsCase.Status.READY)
        self.assertEqual(case.category, OperationsCase.Category.CHANGE)
        self.assertEqual(case.summary, "予約一覧の視認性を改善したい要望")
        send_line.assert_called_once()
        slack.assert_called_once_with(case)
        notion.assert_called_once_with(case)
        self.assertEqual(case.messages.filter(role=OperationsCaseMessage.Role.ASSISTANT).count(), 1)
