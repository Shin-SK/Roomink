from datetime import date, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Cast, Room, ShiftRequest, Store, UserProfile


User = get_user_model()


class ShiftRequestBulkCreateTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="複数日申請店舗", timezone="Asia/Tokyo")
        self.room = Room.objects.create(store=self.store, name="101")
        self.cast_user = User.objects.create_user("bulk_shift_cast", password="pass")
        UserProfile.objects.create(
            user=self.cast_user,
            store=self.store,
            role=UserProfile.Role.CAST,
        )
        self.cast = Cast.objects.create(
            store=self.store,
            user=self.cast_user,
            name="複数日申請キャスト",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.cast_user)
        self.start_date = date(2026, 8, 12)

    def payload(self, **overrides):
        payload = {
            "dates": [
                self.start_date.isoformat(),
                (self.start_date + timedelta(days=2)).isoformat(),
                (self.start_date + timedelta(days=4)).isoformat(),
            ],
            "start_time": "18:00",
            "end_time": "05:00",
            "end_day_offset": 1,
            "desired_room": self.room.id,
            "memo": "同じ内容でまとめて申請",
        }
        payload.update(overrides)
        return payload

    def test_cast_can_create_multiple_shift_requests_with_common_details(self):
        response = self.client.post(
            "/api/cast/shift-requests/bulk-create/",
            self.payload(),
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["created_count"], 3)
        self.assertEqual(len(response.data["created"]), 3)
        self.assertEqual(
            [item["date"] for item in response.data["created"]],
            [
                self.start_date.isoformat(),
                (self.start_date + timedelta(days=2)).isoformat(),
                (self.start_date + timedelta(days=4)).isoformat(),
            ],
        )
        self.assertTrue(
            all(item["end_time_extended"] == "29:00" for item in response.data["created"])
        )
        self.assertEqual(ShiftRequest.objects.filter(cast=self.cast).count(), 3)
        self.assertFalse(
            ShiftRequest.objects.filter(cast=self.cast).exclude(
                start_time=time(18, 0),
                end_time=time(5, 0),
                end_day_offset=1,
                desired_room=self.room,
                memo="同じ内容でまとめて申請",
            ).exists()
        )

    def test_duplicate_dates_are_rejected_without_creating_any_rows(self):
        duplicated = self.start_date.isoformat()
        response = self.client.post(
            "/api/cast/shift-requests/bulk-create/",
            self.payload(dates=[duplicated, duplicated]),
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(ShiftRequest.objects.count(), 0)

    def test_conflict_on_one_date_rolls_back_all_dates(self):
        conflict_date = self.start_date + timedelta(days=2)
        ShiftRequest.objects.create(
            store=self.store,
            cast=self.cast,
            date=conflict_date,
            start_time=time(18, 0),
            end_time=time(5, 0),
            end_day_offset=1,
        )

        response = self.client.post(
            "/api/cast/shift-requests/bulk-create/",
            self.payload(),
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(ShiftRequest.objects.count(), 1)

    def test_room_from_another_store_is_rejected_without_creating_rows(self):
        other_store = Store.objects.create(name="別店舗")
        other_room = Room.objects.create(store=other_store, name="201")

        response = self.client.post(
            "/api/cast/shift-requests/bulk-create/",
            self.payload(desired_room=other_room.id),
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(ShiftRequest.objects.count(), 0)

    def test_more_than_31_dates_are_rejected(self):
        dates = [
            (self.start_date + timedelta(days=offset)).isoformat()
            for offset in range(32)
        ]

        response = self.client.post(
            "/api/cast/shift-requests/bulk-create/",
            self.payload(dates=dates),
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(ShiftRequest.objects.count(), 0)

    def test_non_cast_user_cannot_create_multiple_shift_requests(self):
        manager = User.objects.create_user("bulk_shift_manager", password="pass")
        UserProfile.objects.create(
            user=manager,
            store=self.store,
            role=UserProfile.Role.MANAGER,
        )
        client = APIClient()
        client.force_authenticate(manager)

        response = client.post(
            "/api/cast/shift-requests/bulk-create/",
            self.payload(),
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(ShiftRequest.objects.count(), 0)

    def test_existing_single_date_endpoint_still_works(self):
        response = self.client.post(
            "/api/cast/shift-requests/",
            {
                "date": self.start_date.isoformat(),
                "start_time": "18:00",
                "end_time": "23:00",
                "end_day_offset": 0,
                "desired_room": self.room.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(ShiftRequest.objects.count(), 1)
