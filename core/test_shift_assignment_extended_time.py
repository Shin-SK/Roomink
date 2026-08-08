from datetime import date, time

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Cast, Room, ShiftAssignment, Store, UserProfile


User = get_user_model()


class ShiftAssignmentExtendedTimeTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="深夜営業店舗", timezone="Asia/Tokyo")
        self.other_store = Store.objects.create(name="別店舗", timezone="Asia/Tokyo")
        self.cast = Cast.objects.create(store=self.store, name="深夜キャスト")
        self.room = Room.objects.create(store=self.store, name="101")
        self.other_room = Room.objects.create(store=self.other_store, name="別店舗ルーム")
        self.manager = User.objects.create_user("extended_shift_manager", password="pass")
        UserProfile.objects.create(
            user=self.manager,
            store=self.store,
            role=UserProfile.Role.MANAGER,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.manager)
        self.shift_date = date(2026, 7, 31)

    def payload(self, **overrides):
        payload = {
            "date": self.shift_date.isoformat(),
            "cast": self.cast.id,
            "room": self.room.id,
            "start_time": "11:00",
            "end_time": "05:00",
            "end_day_offset": 1,
        }
        payload.update(overrides)
        return payload

    def test_manager_can_create_and_read_shift_ending_at_29(self):
        response = self.client.post("/api/shifts/", self.payload(), format="json")

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["end_time"], "05:00:00")
        self.assertEqual(response.data["end_day_offset"], 1)
        self.assertEqual(response.data["end_time_extended"], "29:00")

        shift = ShiftAssignment.objects.get(pk=response.data["id"])
        self.assertEqual(shift.end_time, time(5, 0))
        self.assertEqual(shift.end_day_offset, 1)

        detail = self.client.get(f"/api/shifts/{shift.id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["end_time_extended"], "29:00")

    def test_existing_same_day_shift_keeps_legacy_api_fields(self):
        response = self.client.post(
            "/api/shifts/",
            self.payload(end_time="23:00", end_day_offset=0),
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["end_time"], "23:00:00")
        self.assertEqual(response.data["end_day_offset"], 0)
        self.assertEqual(response.data["end_time_extended"], "23:00")

    def test_shift_can_be_updated_from_same_day_to_29(self):
        shift = ShiftAssignment.objects.create(
            store=self.store,
            date=self.shift_date,
            cast=self.cast,
            room=self.room,
            start_time=time(11, 0),
            end_time=time(23, 0),
        )

        response = self.client.patch(
            f"/api/shifts/{shift.id}/",
            {"end_time": "05:00", "end_day_offset": 1},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["end_time_extended"], "29:00")
        shift.refresh_from_db()
        self.assertEqual(shift.end_time, time(5, 0))
        self.assertEqual(shift.end_day_offset, 1)

    def test_end_after_29_is_rejected(self):
        response = self.client.post(
            "/api/shifts/",
            self.payload(end_time="05:01"),
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(ShiftAssignment.objects.count(), 0)

    def test_same_day_end_before_start_is_rejected(self):
        response = self.client.post(
            "/api/shifts/",
            self.payload(end_time="05:00", end_day_offset=0),
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(ShiftAssignment.objects.count(), 0)

    def test_overlap_with_next_calendar_date_is_rejected(self):
        ShiftAssignment.objects.create(
            store=self.store,
            date=self.shift_date,
            cast=self.cast,
            room=self.room,
            start_time=time(11, 0),
            end_time=time(5, 0),
            end_day_offset=1,
        )

        response = self.client.post(
            "/api/shifts/",
            self.payload(
                date="2026-08-01",
                start_time="01:00",
                end_time="04:00",
                end_day_offset=0,
            ),
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(ShiftAssignment.objects.count(), 1)

    def test_other_store_room_is_still_rejected(self):
        response = self.client.post(
            "/api/shifts/",
            self.payload(room=self.other_room.id),
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(ShiftAssignment.objects.count(), 0)
