import base64
import hashlib
import hmac
import json
from datetime import date, datetime, time
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import (
    Cast,
    LineNotificationLog,
    Room,
    ShiftAssignment,
    Store,
    UserProfile,
)
from core.services.shift_end_line_notifications import send_shift_end_line_alerts


User = get_user_model()
TOKYO = ZoneInfo("Asia/Tokyo")


class ShiftEndLineAlertTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(
            name="LINE終了通知店",
            timezone="Asia/Tokyo",
            line_is_enabled=True,
            line_channel_secret="test-secret",
            line_channel_access_token="test-access-token",
            line_shift_end_alert_enabled=True,
            line_operations_recipient_id="C-operations-group",
            line_operations_recipient_type=Store.LineOperationsRecipientType.GROUP,
        )
        self.room = Room.objects.create(store=self.store, name="101")
        self.cast = Cast.objects.create(store=self.store, name="終了確認キャスト")
        self.shift = ShiftAssignment.objects.create(
            store=self.store,
            date=date(2026, 8, 16),
            cast=self.cast,
            room=self.room,
            start_time=time(18, 0),
            end_time=time(22, 0),
        )

    def at(self, hour, minute=0):
        return datetime(2026, 8, 16, hour, minute, tzinfo=TOKYO)

    @patch("core.services.line_notify.http_requests.post")
    def test_open_alert_is_sent_to_operations_recipient_once(self, post):
        post.return_value = Mock(status_code=200, text="")

        first = send_shift_end_line_alerts(self.store, reference_at=self.at(20, 50))
        second = send_shift_end_line_alerts(self.store, reference_at=self.at(20, 55))

        self.assertEqual(first["sent"], 1)
        self.assertEqual(second["sent"], 0)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.kwargs["json"]["to"], "C-operations-group")
        message = post.call_args.kwargs["json"]["messages"][0]["text"]
        self.assertIn(self.cast.name, message)
        self.assertIn("22:00", message)
        self.assertIn("70分前", message)
        self.assertEqual(
            LineNotificationLog.objects.filter(
                shift_assignment=self.shift,
                notification_type=LineNotificationLog.NotificationType.SHIFT_END_70,
                status=LineNotificationLog.Status.SENT,
            ).count(),
            1,
        )

    @patch("core.services.line_notify.http_requests.post")
    def test_missing_recipient_fails_closed_without_sent_log(self, post):
        self.store.line_operations_recipient_id = ""
        self.store.save(update_fields=["line_operations_recipient_id"])

        result = send_shift_end_line_alerts(self.store, reference_at=self.at(20, 50))

        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["configuration_missing"], 1)
        post.assert_not_called()
        self.assertFalse(
            LineNotificationLog.objects.filter(
                notification_type=LineNotificationLog.NotificationType.SHIFT_END_70,
                status=LineNotificationLog.Status.SENT,
            ).exists()
        )

    @patch("core.services.line_notify.http_requests.post")
    def test_existing_alert_is_not_sent_after_shift_end(self, post):
        self.store.line_operations_recipient_id = ""
        self.store.save(update_fields=["line_operations_recipient_id"])
        send_shift_end_line_alerts(self.store, reference_at=self.at(20, 50))
        self.store.line_operations_recipient_id = "C-operations-group"
        self.store.save(update_fields=["line_operations_recipient_id"])

        result = send_shift_end_line_alerts(self.store, reference_at=self.at(22, 1))

        self.assertEqual(result["sent"], 0)
        post.assert_not_called()

    @patch("core.services.line_notify.http_requests.post")
    def test_late_order_prevents_external_notification(self, post):
        from core.models import Course, Customer, Order

        customer = Customer.objects.create(
            store=self.store,
            phone="09011112222",
            display_name="予約者",
        )
        course = Course.objects.create(
            store=self.store,
            name="60分",
            duration=60,
            price=10000,
        )
        Order.objects.create(
            store=self.store,
            cast=self.cast,
            room=self.room,
            customer=customer,
            course=course,
            course_name=course.name,
            course_price=course.price,
            total_price=course.price,
            start=self.at(20, 30),
            end=self.at(21, 30),
            status=Order.Status.CONFIRMED,
        )

        result = send_shift_end_line_alerts(self.store, reference_at=self.at(20, 50))

        self.assertEqual(result["sent"], 0)
        post.assert_not_called()

    @patch("core.views._line_reply")
    def test_operations_group_can_be_linked_with_one_time_code(self, reply):
        original_code = self.store.line_operations_link_code
        body = {
            "events": [
                {
                    "type": "message",
                    "replyToken": "reply-token",
                    "source": {
                        "type": "group",
                        "groupId": "C-new-operations-group",
                        "userId": "U-manager",
                    },
                    "message": {"type": "text", "text": original_code.lower()},
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
        self.store.refresh_from_db()
        self.assertEqual(
            self.store.line_operations_recipient_id,
            "C-new-operations-group",
        )
        self.assertEqual(
            self.store.line_operations_recipient_type,
            Store.LineOperationsRecipientType.GROUP,
        )
        self.assertIsNotNone(self.store.line_operations_linked_at)
        self.assertNotEqual(self.store.line_operations_link_code, original_code)
        reply.assert_called_once()

    def test_manager_can_unlink_without_recipient_id_being_exposed(self):
        manager = User.objects.create_user("line-alert-manager")
        UserProfile.objects.create(
            user=manager,
            store=self.store,
            role=UserProfile.Role.MANAGER,
        )
        client = APIClient()
        client.force_authenticate(manager)

        get_response = client.get("/api/op/line-settings/")
        old_code = get_response.data["line_operations_link_code"]
        unlink_response = client.patch(
            "/api/op/line-settings/",
            {"line_operations_unlink": True},
            format="json",
        )

        self.assertEqual(get_response.status_code, 200, get_response.data)
        self.assertTrue(get_response.data["line_operations_linked"])
        self.assertNotIn("line_operations_recipient_id", get_response.data)
        self.assertEqual(unlink_response.status_code, 200, unlink_response.data)
        self.store.refresh_from_db()
        self.assertEqual(self.store.line_operations_recipient_id, "")
        self.assertFalse(self.store.line_shift_end_alert_enabled)
        self.assertNotEqual(self.store.line_operations_link_code, old_code)
