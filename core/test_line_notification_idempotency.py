from datetime import date, time
from unittest.mock import Mock, patch

from django.test import TestCase
from django.utils import timezone

from core.models import Cast, LineNotificationLog, Room, ShiftAssignment, Store
from core.services.line_notify import send_line_push_once


class LineNotificationIdempotencyTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(
            name="通知冪等性テスト店",
            timezone="Asia/Tokyo",
            line_is_enabled=True,
            line_channel_access_token="test-access-token",
            line_setup_completed_at=timezone.now(),
            line_started_at=timezone.now(),
        )
        self.room = Room.objects.create(store=self.store, name="101")
        self.cast = Cast.objects.create(
            store=self.store,
            name="通知テストキャスト",
            line_user_id="U-test-cast",
        )
        self.shift = ShiftAssignment.objects.create(
            store=self.store,
            date=date(2030, 1, 15),
            cast=self.cast,
            room=self.room,
            start_time=time(12, 0),
            end_time=time(20, 0),
        )
        self.notification_type = LineNotificationLog.NotificationType.MORNING

    def send_once(self):
        return send_line_push_once(
            self.store.pk,
            self.shift.pk,
            "【Roomink】テスト通知",
            self.notification_type,
        )

    @patch("core.services.line_notify.http_requests.post")
    def test_sent_notification_is_not_sent_again(self, post):
        post.return_value = Mock(status_code=200, text="", headers={})

        first = self.send_once()
        second = self.send_once()

        self.assertEqual(first.status, LineNotificationLog.Status.SENT)
        self.assertIsNone(second)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(
            LineNotificationLog.objects.filter(
                shift_assignment=self.shift,
                notification_type=self.notification_type,
                status=LineNotificationLog.Status.SENT,
            ).count(),
            1,
        )

    @patch("core.services.line_notify.http_requests.post")
    def test_retry_after_ambiguous_failure_reuses_key_and_accepts_line_deduplication(self, post):
        post.side_effect = [
            Mock(status_code=500, text="temporary error", headers={}),
            Mock(
                status_code=409,
                text="already accepted",
                headers={"x-line-accepted-request-id": "accepted-request"},
            ),
        ]

        first = self.send_once()
        second = self.send_once()

        self.assertEqual(first.status, LineNotificationLog.Status.FAILED)
        self.assertEqual(second.status, LineNotificationLog.Status.SENT)
        self.assertEqual(post.call_count, 2)
        first_key = post.call_args_list[0].kwargs["headers"]["X-Line-Retry-Key"]
        second_key = post.call_args_list[1].kwargs["headers"]["X-Line-Retry-Key"]
        self.assertEqual(first_key, second_key)
        self.assertEqual(
            LineNotificationLog.objects.filter(
                shift_assignment=self.shift,
                notification_type=self.notification_type,
                status=LineNotificationLog.Status.SENT,
            ).count(),
            1,
        )
