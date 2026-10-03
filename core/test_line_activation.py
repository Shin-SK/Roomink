import base64
import hashlib
import hmac
import json
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Cast, Store, UserProfile


User = get_user_model()


class StoreLineActivationApiTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(
            name="開始待ち店舗",
            slug="line-ready-store",
            line_is_enabled=True,
            line_add_friend_url="https://line.me/R/ti/p/test",
            line_channel_secret="test-secret",
            line_channel_access_token="test-token",
            line_setup_completed_at=timezone.now(),
        )
        self.other_store = Store.objects.create(
            name="別店舗",
            slug="other-store",
            line_is_enabled=True,
            line_setup_completed_at=timezone.now(),
        )
        self.manager = User.objects.create_user("line-start-manager")
        UserProfile.objects.create(
            user=self.manager,
            store=self.store,
            role=UserProfile.Role.MANAGER,
        )
        self.staff = User.objects.create_user("line-start-staff")
        UserProfile.objects.create(
            user=self.staff,
            store=self.store,
            role=UserProfile.Role.STAFF,
        )

    def test_manager_can_start_ready_store_once_without_touching_other_store(self):
        client = APIClient()
        client.force_authenticate(self.manager)

        before = client.get("/api/op/line-activation/")
        first = client.post("/api/op/line-activation/", {}, format="json")
        self.store.refresh_from_db()
        started_at = self.store.line_started_at
        second = client.post("/api/op/line-activation/", {}, format="json")
        self.store.refresh_from_db()
        self.other_store.refresh_from_db()

        self.assertEqual(before.status_code, 200, before.data)
        self.assertEqual(before.data["status"], "ready")
        self.assertTrue(before.data["can_start"])
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(first.data["status"], "active")
        self.assertIsNotNone(started_at)
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(self.store.line_started_at, started_at)
        self.assertIsNone(self.other_store.line_started_at)

    def test_manager_cannot_start_before_roomink_marks_setup_ready(self):
        self.store.line_setup_completed_at = None
        self.store.save(update_fields=["line_setup_completed_at"])
        client = APIClient()
        client.force_authenticate(self.manager)

        response = client.post("/api/op/line-activation/", {}, format="json")

        self.assertEqual(response.status_code, 409, response.data)
        self.store.refresh_from_db()
        self.assertIsNone(self.store.line_started_at)

    def test_staff_cannot_read_or_start_line_activation(self):
        client = APIClient()
        client.force_authenticate(self.staff)

        self.assertEqual(client.get("/api/op/line-activation/").status_code, 403)
        self.assertEqual(client.post("/api/op/line-activation/", {}, format="json").status_code, 403)


class PlatformLineReadinessTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(
            name="接続テスト店舗",
            slug="line-setup-store",
            line_is_enabled=True,
            line_add_friend_url="https://line.me/R/ti/p/test",
            line_channel_secret="test-secret",
            line_channel_access_token="test-token",
            line_setup_completed_at=timezone.now(),
            line_started_at=timezone.now(),
        )
        self.admin = User.objects.create_superuser("line-platform-admin", password="test-secret")
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        session = self.client.session
        session["platform_store_id"] = self.store.id
        session.save()

    def test_platform_admin_can_return_active_store_to_ready(self):
        response = self.client.patch(
            "/api/op/line-settings/",
            {"line_mark_ready": True},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["line_activation_status"], "ready")
        self.store.refresh_from_db()
        self.assertIsNotNone(self.store.line_setup_completed_at)
        self.assertIsNone(self.store.line_started_at)

    def test_changing_credentials_requires_connection_test_again(self):
        response = self.client.patch(
            "/api/op/line-settings/",
            {"line_channel_secret": "changed-secret"},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["line_activation_status"], "preparing")
        self.store.refresh_from_db()
        self.assertIsNone(self.store.line_setup_completed_at)
        self.assertIsNone(self.store.line_started_at)

    def test_ready_requires_complete_connection_settings(self):
        self.store.line_add_friend_url = ""
        self.store.save(update_fields=["line_add_friend_url"])

        response = self.client.patch(
            "/api/op/line-settings/",
            {"line_mark_ready": True},
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("友だち追加URL", response.data["detail"])


class LineWebhookBeforeStartTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(
            name="開始前Webhook店舗",
            slug="line-webhook-before-start",
            line_is_enabled=True,
            line_channel_secret="test-secret",
            line_channel_access_token="test-token",
            line_setup_completed_at=timezone.now(),
        )
        self.cast = Cast.objects.create(store=self.store, name="開始前キャスト")

    @patch("core.views._line_reply")
    def test_webhook_verify_succeeds_but_user_message_is_ignored_before_start(self, reply):
        body = {
            "events": [
                {
                    "type": "message",
                    "replyToken": "reply-token",
                    "source": {"type": "user", "userId": "U-before-start"},
                    "message": {"type": "text", "text": self.cast.line_link_code},
                },
            ],
        }
        raw_body = json.dumps(body).encode("utf-8")
        digest = hmac.new(
            self.store.line_channel_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).digest()
        signature = base64.b64encode(digest).decode("utf-8")

        response = APIClient().generic(
            "POST",
            f"/api/webhook/line/{self.store.line_webhook_token}/",
            raw_body,
            content_type="application/json",
            HTTP_X_LINE_SIGNATURE=signature,
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "not_started")
        self.cast.refresh_from_db()
        self.assertIsNone(self.cast.line_user_id)
        reply.assert_not_called()


class LineReminderActivationGateTest(TestCase):
    @patch(
        "core.management.commands.send_line_reminders.send_shift_end_line_alerts",
        return_value={"sent": 0},
    )
    def test_scheduler_processes_only_started_stores(self, send_shift_end_alerts):
        ready_store = Store.objects.create(
            name="開始待ち店舗",
            slug="reminder-ready-store",
            line_is_enabled=True,
            line_setup_completed_at=timezone.now(),
        )
        active_store = Store.objects.create(
            name="利用中店舗",
            slug="reminder-active-store",
            line_is_enabled=True,
            line_setup_completed_at=timezone.now(),
            line_started_at=timezone.now(),
        )

        call_command("send_line_reminders", stdout=StringIO())

        send_shift_end_alerts.assert_called_once()
        self.assertEqual(send_shift_end_alerts.call_args.args[0], active_store)
        self.assertNotEqual(send_shift_end_alerts.call_args.args[0], ready_store)
