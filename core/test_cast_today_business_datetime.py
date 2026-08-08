from datetime import date, datetime, time
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import (
    Cast,
    Course,
    Customer,
    Order,
    Room,
    ShiftAssignment,
    Store,
    UserProfile,
)


User = get_user_model()
TOKYO = ZoneInfo("Asia/Tokyo")


class CastTodayBusinessDateTimeTest(TestCase):
    def setUp(self):
        self.business_date = date(2026, 7, 31)
        self.store = Store.objects.create(name="深夜キャスト店舗", timezone="Asia/Tokyo")
        cast_user = User.objects.create_user("late_cast_today", password="pass")
        UserProfile.objects.create(
            user=cast_user,
            store=self.store,
            role=UserProfile.Role.CAST,
        )
        self.cast = Cast.objects.create(
            store=self.store,
            user=cast_user,
            name="深夜キャスト",
        )
        self.room = Room.objects.create(store=self.store, name="101")
        self.customer = Customer.objects.create(
            store=self.store,
            phone="09044445555",
            display_name="深夜予約者",
        )
        self.course = Course.objects.create(
            store=self.store,
            name="60分",
            duration=60,
            price=10000,
        )
        ShiftAssignment.objects.create(
            store=self.store,
            date=self.business_date,
            cast=self.cast,
            room=self.room,
            start_time=time(11, 0),
            end_time=time(5, 0),
            end_day_offset=1,
        )
        self.late_order = Order.objects.create(
            store=self.store,
            cast=self.cast,
            room=self.room,
            customer=self.customer,
            course=self.course,
            course_name=self.course.name,
            course_price=self.course.price,
            total_price=self.course.price,
            start=datetime(2026, 8, 1, 3, 0, tzinfo=TOKYO),
            end=datetime(2026, 8, 1, 4, 0, tzinfo=TOKYO),
            status=Order.Status.CONFIRMED,
        )
        self.next_business_order = Order.objects.create(
            store=self.store,
            cast=self.cast,
            room=self.room,
            customer=self.customer,
            course=self.course,
            course_name=self.course.name,
            course_price=self.course.price,
            total_price=self.course.price,
            start=datetime(2026, 8, 1, 5, 0, tzinfo=TOKYO),
            end=datetime(2026, 8, 1, 6, 0, tzinfo=TOKYO),
            status=Order.Status.CONFIRMED,
        )
        self.client = APIClient()
        self.client.force_authenticate(cast_user)

    def assert_late_order_response(self, response):
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["date"], "2026-07-31")
        self.assertEqual(response.data["total_orders"], 1)
        self.assertEqual(response.data["orders"][0]["id"], self.late_order.id)
        self.assertEqual(response.data["orders"][0]["start_time_extended"], "27:00")
        self.assertEqual(response.data["orders"][0]["end_time_extended"], "28:00")
        self.assertEqual(response.data["shift"]["end_time_extended"], "29:00")

    def test_requested_business_date_includes_next_calendar_day_order(self):
        response = self.client.get("/api/cast/today/?date=2026-07-31")

        self.assert_late_order_response(response)

    @patch("core.views.timezone.now")
    def test_omitted_date_uses_store_business_date(self, now_mock):
        now_mock.return_value = datetime(2026, 8, 1, 3, 30, tzinfo=TOKYO)

        response = self.client.get("/api/cast/today/")

        self.assert_late_order_response(response)

    def test_ack_response_keeps_extended_business_time(self):
        response = self.client.post(f"/api/cast/orders/{self.late_order.id}/ack/")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["start_time_extended"], "27:00")
        self.assertEqual(response.data["end_time_extended"], "28:00")

    @patch("core.views.timezone.now")
    def test_shift_confirmation_uses_store_business_date(self, now_mock):
        now_mock.return_value = datetime(2026, 8, 1, 3, 30, tzinfo=TOKYO)

        response = self.client.get("/api/cast/shift-confirm/")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["shift"]["date"], "2026-07-31")
        self.assertEqual(response.data["shift"]["end_time_extended"], "29:00")
        self.assertTrue(response.data["is_today"])
