from datetime import date, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import (
    Area,
    Cast,
    CastAreaPreference,
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
        self.shibuya_area = Area.objects.create(store=self.store, name="渋谷")
        self.shinjuku_area = Area.objects.create(store=self.store, name="新宿")
        self.shibuya = Room.objects.create(
            store=self.store, name="渋谷101", area=self.shibuya_area, sort_order=1,
        )
        self.shinjuku = Room.objects.create(
            store=self.store, name="新宿201", area=self.shinjuku_area, sort_order=2,
        )
        self.fallback = Room.objects.create(
            store=self.store, name="その他301", area_name="", sort_order=0,
        )
        self.cast = Cast.objects.create(
            store=self.store,
            name="希望ありキャスト",
        )
        CastAreaPreference.objects.create(cast=self.cast, area=self.shinjuku_area, rank=1)
        CastAreaPreference.objects.create(cast=self.cast, area=self.shibuya_area, rank=2)
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

    def test_auto_assigns_the_first_available_preferred_area(self):
        response = self.client.post("/api/shifts/", self.shift_payload(), format="json")

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["room"], self.shinjuku.id)
        self.assertTrue(response.data["room_auto_assigned"])

    def test_does_not_spill_into_an_unpreferred_area(self):
        self.block_room_with_shift(self.shinjuku)
        self.block_room_with_shift(self.shibuya)

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

    def test_area_selection_assigns_an_available_room_in_that_area(self):
        response = self.client.post(
            "/api/shifts/",
            self.shift_payload(requested_area=self.shibuya_area.id),
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["room"], self.shibuya.id)
        self.assertTrue(response.data["room_auto_assigned"])

    def test_legacy_direct_room_selection_is_preserved(self):
        response = self.client.post(
            "/api/shifts/",
            self.shift_payload(room=self.shinjuku.id),
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["room"], self.shinjuku.id)
        self.assertFalse(response.data["room_auto_assigned"])

    def test_weekly_input_auto_assigns_by_preferred_area(self):
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
                    },
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["created"][0]["room"], self.shinjuku.id)
        self.assertTrue(response.data["created"][0]["room_auto_assigned"])

    def test_shift_request_approval_auto_assigns_by_preferred_area(self):
        request_obj = ShiftRequest.objects.create(
            store=self.store,
            cast=self.cast,
            date=self.target_date,
            start_time=time(18, 0),
            end_time=time(23, 0),
        )

        response = self.client.post(
            f"/api/op/shift-requests/{request_obj.id}/approve/",
            {},
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
