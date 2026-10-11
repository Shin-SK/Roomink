from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Cast, Course, Customer, Order, Room, ShiftAssignment, Store, UserProfile


TOKYO = ZoneInfo("Asia/Tokyo")
User = get_user_model()


class ExtendedShiftStartAndBusinessDaySettingsTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="深夜店舗", timezone="Asia/Tokyo")
        self.cast = Cast.objects.create(store=self.store, name="深夜キャスト")
        self.room = Room.objects.create(store=self.store, name="101")
        self.customer = Customer.objects.create(store=self.store, phone="09011112222")
        self.course = Course.objects.create(store=self.store, name="60分", duration=60, price=10000)
        self.user = User.objects.create_user("extended_shift_manager", password="pass")
        UserProfile.objects.create(user=self.user, store=self.store, role=UserProfile.Role.MANAGER)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_shift_can_start_at_24_00_and_timeline_serializes_extended_start(self):
        response = self.client.post("/api/shifts/", {
            "date": "2026-10-10",
            "cast": self.cast.id,
            "room": self.room.id,
            "start_time": "00:00",
            "start_day_offset": 1,
            "end_time": "02:00",
            "end_day_offset": 1,
        }, format="json")

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["start_time_extended"], "24:00")
        self.assertEqual(response.data["end_time_extended"], "26:00")

        timeline = self.client.get("/api/op/schedule/?date=2026-10-10")
        self.assertEqual(timeline.status_code, 200, timeline.data)
        self.assertEqual(timeline.data["casts"][0]["shifts"][0]["start_time_extended"], "24:00")

    def test_configured_boundary_changes_timeline_range(self):
        self.store.business_day_boundary_hour = 4
        self.store.save(update_fields=["business_day_boundary_hour"])
        ShiftAssignment.objects.create(
            store=self.store, date=date(2026, 10, 10), cast=self.cast, room=self.room,
            start_time=time(18, 0), end_time=time(4, 0), end_day_offset=1,
        )
        Order.objects.create(
            store=self.store, cast=self.cast, room=self.room, customer=self.customer,
            course=self.course, course_name="60分", course_price=10000, total_price=10000,
            start=datetime(2026, 10, 11, 4, 0, tzinfo=TOKYO),
            end=datetime(2026, 10, 11, 5, 0, tzinfo=TOKYO), status=Order.Status.CONFIRMED,
        )

        timeline = self.client.get("/api/op/schedule/?date=2026-10-10")
        self.assertEqual(timeline.status_code, 200, timeline.data)
        self.assertEqual(timeline.data["orders"], [])

        settings = self.client.patch(
            "/api/op/business-day-settings/", {"business_day_boundary_hour": 5}, format="json",
        )
        self.assertEqual(settings.status_code, 200, settings.data)
        self.assertEqual(settings.data["business_day_boundary_hour"], 5)

    def test_staff_can_read_but_cannot_change_business_day_boundary(self):
        staff = User.objects.create_user("extended_shift_staff", password="pass")
        UserProfile.objects.create(user=staff, store=self.store, role=UserProfile.Role.STAFF)
        self.client.force_authenticate(staff)

        readable = self.client.get("/api/op/business-day-settings/")
        self.assertEqual(readable.status_code, 200, readable.data)

        update = self.client.patch(
            "/api/op/business-day-settings/", {"business_day_boundary_hour": 4}, format="json",
        )
        self.assertEqual(update.status_code, 403, update.data)
