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


class RoomOptionalTest(TestCase):
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

    def test_allows_shift_without_a_room(self):
        response = self.client.post("/api/shifts/", self.shift_payload(), format="json")

        self.assertEqual(response.status_code, 201, response.data)
        self.assertIsNone(response.data["room"])
        self.assertFalse(response.data["room_auto_assigned"])

    def test_allows_shift_without_a_room_even_when_every_room_is_busy(self):
        self.block_room_with_shift(self.shinjuku)
        self.block_room_with_shift(self.shibuya)
        self.block_room_with_shift(self.fallback)

        response = self.client.post("/api/shifts/", self.shift_payload(), format="json")

        self.assertEqual(response.status_code, 201, response.data)
        self.assertIsNone(response.data["room"])

    def test_manual_room_selection_is_preserved(self):
        response = self.client.post(
            "/api/shifts/",
            self.shift_payload(room=self.fallback.id),
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["room"], self.fallback.id)
        self.assertFalse(response.data["room_auto_assigned"])

    def test_weekly_input_allows_a_room_to_be_unset(self):
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
        self.assertIsNone(response.data["created"][0]["room"])
        self.assertFalse(response.data["created"][0]["room_auto_assigned"])

    def test_shift_request_approval_allows_a_room_to_be_unset(self):
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
        self.assertIsNone(request_obj.approved_room)
        self.assertTrue(
            ShiftAssignment.objects.filter(
                cast=self.cast,
                room__isnull=True,
                date=self.target_date,
            ).exists()
        )
