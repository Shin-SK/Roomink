from datetime import datetime, timedelta, timezone as datetime_timezone

from django.test import TestCase, override_settings

from core.models import Cast, Course, Customer, Order, Room, SmsTemplate, Store
from core.services.notify import (
    build_confirmation_body,
    notify_cast_order,
    notify_order_cancelled,
)


@override_settings(SMS_DUMMY_MODE=False)
class NotificationTimezoneTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="通知時刻テスト店舗", timezone="Asia/Tokyo")
        cast = Cast.objects.create(store=self.store, name="テストキャスト")
        room = Room.objects.create(store=self.store, name="テストルーム")
        customer = Customer.objects.create(
            store=self.store,
            display_name="テスト顧客",
            phone="09000000000",
        )
        course = Course.objects.create(
            store=self.store,
            name="60分コース",
            duration=60,
            price=10000,
        )
        start = datetime(2099, 12, 31, 3, 0, tzinfo=datetime_timezone.utc)
        self.order = Order.objects.create(
            store=self.store,
            cast=cast,
            room=room,
            customer=customer,
            course=course,
            course_name=course.name,
            course_price=course.price,
            total_price=course.price,
            start=start,
            end=start + timedelta(minutes=90),
            payment_method=Order.PaymentMethod.CASH,
        )

    def assert_tokyo_time(self, body):
        self.assertIn("2099-12-31 12:00〜13:30", body)
        self.assertNotIn("2099-12-31 03:00〜04:30", body)

    def test_default_confirmation_uses_store_timezone(self):
        self.assert_tokyo_time(build_confirmation_body(self.order))

    def test_confirmation_template_uses_store_timezone(self):
        SmsTemplate.objects.create(
            store=self.store,
            template_type=SmsTemplate.TemplateType.RESERVATION_CONFIRMATION,
            payment_method=Order.PaymentMethod.CASH,
            body="{date} {start_time}〜{end_time}",
            is_active=True,
        )

        self.assert_tokyo_time(build_confirmation_body(self.order))

    def test_cast_notice_uses_store_timezone(self):
        log = notify_cast_order(self.order)

        self.assert_tokyo_time(log.body)

    def test_cancellation_notice_uses_store_timezone(self):
        log = notify_order_cancelled(self.order)

        self.assert_tokyo_time(log.body)
