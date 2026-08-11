from datetime import date, time, timedelta

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
    ShiftRequest,
    Store,
    UserProfile,
)
from core.services.business_datetime import build_store_datetime


User = get_user_model()


class RoomAutoAssignmentTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="自動割当店舗", timezone="Asia/Tokyo")
        self.shibuya = Room.objects.create(
            store=self.store, name="渋谷101", area_name="渋谷", sort_order=1,
        )
        self.shinjuku = Room.objects.create(
            store=self.store, name="新宿201", area_name="新宿", sort_order=2,
        )
        self.fallback = Room.objects.create(
            store=self.store, name="その他301", area_name="", sort_order=0,
        )
        self.cast = Cast.objects.create(
            store=self.store,
            name="希望ありキャスト",
            preferred_area_1="新宿",
            preferred_area_2="渋谷",
        )
        self.other_cast = Cast.objects.create(store=self.store, name="別キャスト")
        self.manager = User.objects.create_user("room_auto_manager", password="pass")
        UserProfile.objects.create(
            user=self.manager,
            store=self.store,
            role=UserProfile.Role.MANAGER,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.manager)
        self.target_date = date(2026, 8, 20)

    def shift_payload(self, **overrides):
        payload = {
            "date": self.target_date.isoformat(),
            "cast": self.cast.id,
            "room": None,
            "start_time": "18:00",
            "end_time": "23:00",
        }
        payload.update(overrides)
        return payload

    def block_room_with_shift(self, room, start=time(18, 0), end=time(23, 0)):
        return ShiftAssignment.objects.create(
            store=self.store,
            date=self.target_date,
            cast=Cast.objects.create(store=self.store, name=f"block-{room.id}"),
            room=room,
            start_time=start,
            end_time=end,
        )

    def test_auto_assigns_first_preferred_available_area(self):
        response = self.client.post("/api/shifts/", self.shift_payload(), format="json")

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["room"], self.shinjuku.id)
        self.assertTrue(response.data["room_auto_assigned"])

    def test_auto_falls_back_to_second_preference_when_first_is_busy(self):
        self.block_room_with_shift(self.shinjuku)

        response = self.client.post("/api/shifts/", self.shift_payload(), format="json")

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["room"], self.shibuya.id)

    def test_active_order_blocks_room_and_unranked_room_is_fallback(self):
        self.block_room_with_shift(self.shibuya)
        customer = Customer.objects.create(
            store=self.store, phone="09011112222", display_name="顧客",
        )
        course = Course.objects.create(
            store=self.store, name="60分", duration=60, price=10000,
        )
        start = build_store_datetime(
            self.target_date, time(19, 0), timezone_name=self.store.timezone,
        )
        Order.objects.create(
            store=self.store,
            cast=self.other_cast,
            room=self.shinjuku,
            customer=customer,
            course=course,
            course_name=course.name,
            course_price=course.price,
            total_price=course.price,
            start=start,
            end=start + timedelta(hours=1),
            status=Order.Status.CONFIRMED,
        )

        response = self.client.post("/api/shifts/", self.shift_payload(), format="json")

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["room"], self.fallback.id)

    def test_auto_rejects_when_all_rooms_are_busy(self):
        self.block_room_with_shift(self.shinjuku)
        self.block_room_with_shift(self.shibuya)
        self.block_room_with_shift(self.fallback)

        response = self.client.post("/api/shifts/", self.shift_payload(), format="json")

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("room", response.data)
        self.assertFalse(ShiftAssignment.objects.filter(cast=self.cast).exists())

    def test_manual_room_selection_is_preserved(self):
        response = self.client.post(
            "/api/shifts/",
            self.shift_payload(room=self.fallback.id),
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["room"], self.fallback.id)
        self.assertFalse(response.data["room_auto_assigned"])

    def test_weekly_input_can_auto_assign(self):
        response = self.client.post(
            "/api/op/shifts/weekly/",
            {
                "cast": self.cast.id,
                "week_start": "2026-08-17",
                "items": [
                    {
                        "date": self.target_date.isoformat(),
                        "enabled": True,
                        "start_time": "18:00",
                        "end_time": "23:00",
                        "room": None,
                    },
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["created"][0]["room"], self.shinjuku.id)
        self.assertTrue(response.data["created"][0]["room_auto_assigned"])

    def test_shift_request_approval_can_auto_assign(self):
        request_obj = ShiftRequest.objects.create(
            store=self.store,
            cast=self.cast,
            date=self.target_date,
            start_time=time(18, 0),
            end_time=time(23, 0),
        )

        response = self.client.post(
            f"/api/op/shift-requests/{request_obj.id}/approve/",
            {"room": None},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.approved_room, self.shinjuku)
        self.assertTrue(
            ShiftAssignment.objects.filter(
                cast=self.cast,
                room=self.shinjuku,
                date=self.target_date,
            ).exists()
        )
