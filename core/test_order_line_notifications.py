from datetime import datetime, timedelta, timezone as datetime_timezone
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Cast, Course, Customer, LineNotificationLog, Order, Room, Store, UserProfile
from core.services.line_notify import send_order_confirmation_push_once


class OrderLineNotificationTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(
            name="予約LINE通知テスト店",
            timezone="Asia/Tokyo",
            line_is_enabled=True,
            line_channel_access_token="test-access-token",
            line_setup_completed_at=timezone.now(),
            line_started_at=timezone.now(),
        )
        self.cast = Cast.objects.create(
            store=self.store,
            name="通知テストキャスト",
            line_user_id="U-test-cast",
        )
        self.room = Room.objects.create(store=self.store, name="101")
        self.customer = Customer.objects.create(
            store=self.store,
            display_name="通知テスト顧客",
            phone="09000000000",
        )
        self.course = Course.objects.create(
            store=self.store,
            name="90分コース",
            duration=90,
            price=12000,
        )
        self.order = Order.objects.create(
            store=self.store,
            cast=self.cast,
            room=self.room,
            customer=self.customer,
            course=self.course,
            course_name=self.course.name,
            course_price=self.course.price,
            total_price=self.course.price,
            start=datetime(2099, 12, 31, 3, 0, tzinfo=datetime_timezone.utc),
            end=datetime(2099, 12, 31, 4, 30, tzinfo=datetime_timezone.utc),
            status=Order.Status.CONFIRMED,
        )

    @patch("core.services.line_notify.http_requests.post")
    def test_sends_one_direct_message_without_customer_information(self, post):
        post.return_value = Mock(status_code=200, text="", headers={})

        first = send_order_confirmation_push_once(self.order.pk)
        second = send_order_confirmation_push_once(self.order.pk)

        self.assertEqual(first.status, LineNotificationLog.Status.SENT)
        self.assertIsNone(second)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.kwargs["json"]["to"], self.cast.line_user_id)
        body = post.call_args.kwargs["json"]["messages"][0]["text"]
        self.assertIn("2099/12/31", body)
        self.assertIn("12:00〜13:30", body)
        self.assertIn("90分コース", body)
        self.assertIn("101", body)
        self.assertNotIn(self.customer.display_name, body)
        self.assertNotIn(self.customer.phone, body)

    @patch("core.services.line_notify.http_requests.post")
    def test_unlinked_cast_is_logged_without_external_send(self, post):
        self.cast.line_user_id = ""
        self.cast.save(update_fields=["line_user_id"])

        log = send_order_confirmation_push_once(self.order.pk)

        self.assertEqual(log.status, LineNotificationLog.Status.SKIPPED)
        self.assertEqual(log.error_message, "LINE未連携")
        post.assert_not_called()

    @patch("core.services.line_notify.http_requests.post")
    def test_line_failure_does_not_change_confirmed_order(self, post):
        post.return_value = Mock(status_code=500, text="temporary", headers={})

        log = send_order_confirmation_push_once(self.order.pk)
        self.order.refresh_from_db()

        self.assertEqual(log.status, LineNotificationLog.Status.FAILED)
        self.assertEqual(self.order.status, Order.Status.CONFIRMED)

    @patch("core.services.line_notify.http_requests.post")
    def test_confirm_endpoint_keeps_order_confirmed_when_line_fails(self, post):
        post.return_value = Mock(status_code=500, text="temporary", headers={})
        user = get_user_model().objects.create_user(
            "line-notification-manager", password="test-pass",
        )
        UserProfile.objects.create(user=user, store=self.store, role=UserProfile.Role.MANAGER)
        self.order.status = Order.Status.REQUESTED
        self.order.save(update_fields=["status", "updated_at"])
        client = APIClient()
        client.force_authenticate(user)

        response = client.post(f"/api/orders/{self.order.pk}/confirm/")
        self.order.refresh_from_db()

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.order.status, Order.Status.CONFIRMED)
        self.assertTrue(LineNotificationLog.objects.filter(
            order=self.order,
            notification_type=LineNotificationLog.NotificationType.ORDER_CONFIRMED,
            status=LineNotificationLog.Status.FAILED,
        ).exists())
