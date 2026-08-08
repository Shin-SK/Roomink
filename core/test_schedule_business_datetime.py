from datetime import date, datetime, time
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


class ScheduleBusinessDateTimeTest(TestCase):
    def setUp(self):
        self.business_date = date(2026, 7, 31)
        self.store = Store.objects.create(name="深夜営業店舗", timezone="Asia/Tokyo")
        self.cast = Cast.objects.create(store=self.store, name="深夜キャスト")
        self.room = Room.objects.create(store=self.store, name="101")
        self.customer = Customer.objects.create(
            store=self.store,
            phone="09033334444",
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
            start_time=time(18, 0),
            end_time=time(5, 0),
            end_day_offset=1,
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
            start=datetime(2026, 8, 1, 3, 0, tzinfo=TOKYO),
            end=datetime(2026, 8, 1, 4, 0, tzinfo=TOKYO),
            status=Order.Status.CONFIRMED,
        )

        manager = User.objects.create_user("schedule_manager", password="pass")
        UserProfile.objects.create(
            user=manager,
            store=self.store,
            role=UserProfile.Role.MANAGER,
        )
        self.client = APIClient()
        self.client.force_authenticate(manager)

    def test_cast_schedule_includes_next_calendar_day_order_in_business_day(self):
        response = self.client.get(
            f"/api/op/schedule/?date={self.business_date.isoformat()}"
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data["orders"]), 1)
        order = response.data["orders"][0]
        self.assertEqual(order["id"], self.order.id)
        self.assertEqual(order["start_time_extended"], "27:00")
        self.assertEqual(order["end_time_extended"], "28:00")
        self.assertEqual(response.data["casts"][0]["shifts"][0]["end_time_extended"], "29:00")

    def test_room_schedule_uses_same_business_day_range(self):
        response = self.client.get(
            f"/api/op/room-schedule/?date={self.business_date.isoformat()}"
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data["orders"]), 1)
        self.assertEqual(response.data["orders"][0]["start_time_extended"], "27:00")
        self.assertEqual(response.data["orders"][0]["end_time_extended"], "28:00")

    def test_next_business_day_does_not_duplicate_previous_days_late_order(self):
        response = self.client.get("/api/op/schedule/?date=2026-08-01")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["orders"], [])
        self.assertEqual(response.data["kpi"]["total_orders"], 0)
