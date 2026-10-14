import base64
import hashlib
import hmac
import json
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Cast, LineRegistrationSession, Store


class ExplicitLineRegistrationTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(
            name="LINE登録検証店", line_is_enabled=True,
            line_channel_secret="registration-test-secret",
            line_channel_access_token="registration-test-token",
            line_setup_completed_at=timezone.now(), line_started_at=timezone.now(),
        )
        self.other = Store.objects.create(
            name="別のLINE店", line_is_enabled=True,
            line_channel_secret="other-registration-test-secret",
            line_channel_access_token="other-registration-test-token",
            line_setup_completed_at=timezone.now(), line_started_at=timezone.now(),
        )
        self.cast = Cast.objects.create(store=self.store, name="登録検証", line_link_code="ABC123")

    def send(self, text=None, *, user="U-registration-test", store=None, source_type="user", event_type="message", signature_valid=True):
        store = store or self.store
        event = {"type": event_type, "replyToken": "test-reply", "source": {"type": source_type, "userId": user}}
        if text is not None:
            event["message"] = {"type": "text", "text": text}
        raw = json.dumps({"events": [event]}).encode()
        sig = base64.b64encode(hmac.new(store.line_channel_secret.encode(), raw, hashlib.sha256).digest()).decode()
        with patch("core.views._line_reply") as reply:
            response = APIClient().generic(
                "POST", f"/api/webhook/line/{store.line_webhook_token}/", raw,
                content_type="application/json", HTTP_X_LINE_SIGNATURE=sig if signature_valid else "invalid",
            )
        self.assertEqual(response.status_code, 200 if signature_valid else 403, response.data)
        return reply.call_args.args[2] if reply.called else None

    def test_follow_inquiry_and_unsolicited_code_are_silent(self):
        self.assertIsNone(self.send(event_type="follow"))
        for text in ("求人について教えてください", "予約したいです", "ABC123", "HELLO1"):
            self.assertIsNone(self.send(text))
        self.cast.refresh_from_db()
        self.assertIsNone(self.cast.line_user_id)
        self.assertEqual(LineRegistrationSession.objects.count(), 0)

    def test_explicit_registration_links_once_and_ends_mode(self):
        self.assertIn("6文字", self.send("登録"))
        self.assertIsNone(self.send("お店への問い合わせです"))
        self.assertIn("完了", self.send("abc123"))
        self.cast.refresh_from_db()
        self.assertEqual(self.cast.line_user_id, "U-registration-test")
        self.assertEqual(LineRegistrationSession.objects.count(), 0)
        self.assertIsNone(self.send("ABC123"))
        self.assertIn("連携済み", self.send("登録"))
        self.assertIsNone(self.send("普通の会話"))

    def test_registration_does_not_authorize_another_person_or_store(self):
        self.send("登録")
        self.assertIsNone(self.send("ABC123", user="U-another-person"))
        self.assertIsNone(self.send("ABC123", store=self.other))
        self.send("登録", store=self.other)
        self.assertIn("無効", self.send("ABC123", store=self.other))
        self.cast.refresh_from_db()
        self.assertIsNone(self.cast.line_user_id)
        self.assertIn("完了", self.send("ABC123"))

    def test_cancel_and_expiry_require_register_again(self):
        self.send("登録")
        self.assertIn("中止", self.send("キャンセル"))
        self.assertIsNone(self.send("ABC123"))
        self.send("登録")
        LineRegistrationSession.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertIsNone(self.send("ABC123"))
        self.assertEqual(LineRegistrationSession.objects.count(), 0)
        self.send("登録")
        self.assertIn("完了", self.send("ABC123"))

    def test_invalid_code_is_only_reported_in_registration_and_limited(self):
        self.send("登録")
        self.assertIsNone(self.send("問い合わせについて"))
        self.assertEqual(LineRegistrationSession.objects.get().failed_attempts, 0)
        for _ in range(4):
            self.assertIn("無効", self.send("ZZZ999"))
        self.assertIn("中止", self.send("ZZZ999"))
        self.assertIsNone(self.send("ABC123"))
        self.assertEqual(LineRegistrationSession.objects.count(), 0)

    def test_groups_and_unsigned_events_do_not_start_registration(self):
        self.assertIsNone(self.send("登録", source_type="group"))
        self.assertIsNone(self.send("登録", signature_valid=False))
        self.assertEqual(LineRegistrationSession.objects.count(), 0)

    def test_expired_state_is_cleaned_and_raw_user_id_is_not_stored(self):
        self.send("登録")
        session = LineRegistrationSession.objects.get()
        self.assertEqual(len(session.identity_key), 64)
        self.assertNotIn("U-registration-test", session.identity_key)
        LineRegistrationSession.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.send("登録", user="U-another-person")
        self.assertEqual(LineRegistrationSession.objects.count(), 1)
