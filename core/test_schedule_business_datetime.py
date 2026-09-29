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
        self.shift = ShiftAssignment.objects.create(
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

    def test_cancelled_order_is_hidden_from_cast_and_room_timelines(self):
        self.order.status = Order.Status.CANCELLED
        self.order.save(update_fields=["status"])

        cast_response = self.client.get(
            f"/api/op/schedule/?date={self.business_date.isoformat()}"
        )
        room_response = self.client.get(
            f"/api/op/room-schedule/?date={self.business_date.isoformat()}"
        )

        self.assertEqual(cast_response.status_code, 200, cast_response.data)
        self.assertEqual(room_response.status_code, 200, room_response.data)
        self.assertEqual(cast_response.data["orders"], [])
        self.assertEqual(room_response.data["orders"], [])
        self.assertEqual(cast_response.data["kpi"]["total_orders"], 0)
        self.assertEqual(room_response.data["kpi"]["total_orders"], 0)

    def test_timeline_status_is_returned_without_changing_order_status(self):
        self.order.timeline_status = Order.TimelineStatus.SMS_CONFIRMED
        self.order.save(update_fields=["timeline_status"])

        response = self.client.get(
            f"/api/op/schedule/?date={self.business_date.isoformat()}"
        )

        self.assertEqual(response.status_code, 200, response.data)
        item = response.data["orders"][0]
        self.assertEqual(item["status"], Order.Status.CONFIRMED)
        self.assertEqual(item["timeline_status"], Order.TimelineStatus.SMS_CONFIRMED)
        self.assertEqual(item["timeline_status_label"], "SMS確認済み")

    def test_shift_absence_can_be_toggled_without_cancelling_existing_order(self):
        update_response = self.client.patch(
            f"/api/shifts/{self.shift.id}/",
            {"is_absent": True},
            format="json",
        )
        self.assertEqual(update_response.status_code, 200, update_response.data)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CONFIRMED)

        schedule_response = self.client.get(
            f"/api/op/schedule/?date={self.business_date.isoformat()}"
        )
        self.assertEqual(schedule_response.status_code, 200, schedule_response.data)
        cast = next(
            item for item in schedule_response.data["casts"]
            if item["id"] == self.cast.id
        )
        self.assertTrue(cast["shifts"][0]["is_absent"])
        self.assertEqual(schedule_response.data["orders"][0]["id"], self.order.id)
