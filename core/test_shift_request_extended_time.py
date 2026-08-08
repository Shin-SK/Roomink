import csv
import io
from datetime import date, time

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import (
    Cast,
    Room,
    ShiftAssignment,
    ShiftRequest,
    Store,
    UserProfile,
)


User = get_user_model()


class ShiftRequestExtendedTimeTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="深夜申請店舗", timezone="Asia/Tokyo")
        self.room = Room.objects.create(store=self.store, name="101")

        self.cast_user = User.objects.create_user("shift_request_cast", password="pass")
        UserProfile.objects.create(
            user=self.cast_user,
            store=self.store,
            role=UserProfile.Role.CAST,
        )
        self.cast = Cast.objects.create(
            store=self.store,
            user=self.cast_user,
            name="深夜申請キャスト",
        )

        self.manager = User.objects.create_user("shift_request_manager", password="pass")
        UserProfile.objects.create(
            user=self.manager,
            store=self.store,
            role=UserProfile.Role.MANAGER,
        )

        self.cast_client = APIClient()
        self.cast_client.force_authenticate(self.cast_user)
        self.manager_client = APIClient()
        self.manager_client.force_authenticate(self.manager)
        self.shift_date = date(2026, 8, 10)

    def request_payload(self, **overrides):
        payload = {
            "date": self.shift_date.isoformat(),
            "start_time": "18:00",
            "end_time": "05:00",
            "end_day_offset": 1,
        }
        payload.update(overrides)
        return payload

    def test_cast_can_request_shift_ending_at_29(self):
        response = self.cast_client.post(
            "/api/cast/shift-requests/",
            self.request_payload(),
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["end_time_extended"], "29:00")
        request = ShiftRequest.objects.get(pk=response.data["id"])
        self.assertEqual(request.end_time, time(5, 0))
        self.assertEqual(request.end_day_offset, 1)

    def test_cast_request_after_29_is_rejected(self):
        response = self.cast_client.post(
            "/api/cast/shift-requests/",
            self.request_payload(end_time="05:01"),
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(ShiftRequest.objects.count(), 0)

    def test_cast_request_rejects_cross_date_pending_overlap(self):
        ShiftRequest.objects.create(
            store=self.store,
            cast=self.cast,
            date=self.shift_date,
            start_time=time(18, 0),
            end_time=time(5, 0),
            end_day_offset=1,
        )

        response = self.cast_client.post(
            "/api/cast/shift-requests/",
            self.request_payload(
                date="2026-08-11",
                start_time="01:00",
                end_time="04:00",
                end_day_offset=0,
            ),
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(ShiftRequest.objects.count(), 1)

    def test_manager_can_approve_shift_ending_at_29(self):
        request = ShiftRequest.objects.create(
            store=self.store,
            cast=self.cast,
            date=self.shift_date,
            start_time=time(18, 0),
            end_time=time(5, 0),
            end_day_offset=1,
        )

        response = self.manager_client.post(
            f"/api/op/shift-requests/{request.id}/approve/",
            {
                "date": self.shift_date.isoformat(),
                "start_time": "18:00",
                "end_time": "05:00",
                "end_day_offset": 1,
                "room": self.room.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["approved_end_time_extended"], "29:00")
        request.refresh_from_db()
        self.assertEqual(request.status, ShiftRequest.Status.APPROVED)
        self.assertEqual(request.approved_end_time, time(5, 0))
        self.assertEqual(request.approved_end_day_offset, 1)

        shift = ShiftAssignment.objects.get(cast=self.cast, date=self.shift_date)
        self.assertEqual(shift.end_time, time(5, 0))
        self.assertEqual(shift.end_day_offset, 1)

    def test_manager_cannot_approve_shift_after_29(self):
        request = ShiftRequest.objects.create(
            store=self.store,
            cast=self.cast,
            date=self.shift_date,
            start_time=time(18, 0),
            end_time=time(23, 0),
        )

        response = self.manager_client.post(
            f"/api/op/shift-requests/{request.id}/approve/",
            {
                "date": self.shift_date.isoformat(),
                "start_time": "18:00",
                "end_time": "05:01",
                "end_day_offset": 1,
                "room": self.room.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        request.refresh_from_db()
        self.assertEqual(request.status, ShiftRequest.Status.REQUESTED)
        self.assertEqual(ShiftAssignment.objects.count(), 0)

    def test_legacy_same_day_request_and_approval_still_work(self):
        response = self.cast_client.post(
            "/api/cast/shift-requests/",
            self.request_payload(end_time="23:00", end_day_offset=0),
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["end_time_extended"], "23:00")

        approve = self.manager_client.post(
            f"/api/op/shift-requests/{response.data['id']}/approve/",
            {
                "room": self.room.id,
                "end_time": "23:00",
                "end_day_offset": 0,
            },
            format="json",
        )
        self.assertEqual(approve.status_code, 200, approve.data)
        self.assertEqual(approve.data["approved_end_time_extended"], "23:00")

    def test_csv_export_preview_and_apply_support_29(self):
        request = ShiftRequest.objects.create(
            store=self.store,
            cast=self.cast,
            date=self.shift_date,
            start_time=time(18, 0),
            end_time=time(5, 0),
            end_day_offset=1,
        )

        exported = self.manager_client.get("/api/op/shift-requests/export_csv/")
        self.assertEqual(exported.status_code, 200)
        rows = list(csv.DictReader(io.StringIO(exported.content.decode("utf-8-sig"))))
        row = next(item for item in rows if int(item["shift_request_id"]) == request.id)
        self.assertEqual(row["requested_end_time"], "29:00")

        csv_content = (
            "shift_request_id,cast_id,approved_date,approved_start_time,"
            "approved_end_time,approved_room_id,admin_memo\n"
            f"{request.id},{self.cast.id},{self.shift_date.isoformat()},"
            f"18:00,29:00,{self.room.id},深夜承認\n"
        )
        upload = io.BytesIO(csv_content.encode("utf-8"))
        upload.name = "shift_requests.csv"
        preview = self.manager_client.post(
            "/api/op/shift-requests/import_preview/",
            {"file": upload},
            format="multipart",
        )
        self.assertEqual(preview.status_code, 200, preview.data)
        preview_row = preview.data["rows"][0]
        self.assertTrue(preview_row["can_apply"], preview_row)

        applied = self.manager_client.post(
            "/api/op/shift-requests/import_apply/",
            {
                "rows": [{
                    "row_number": preview_row["row_number"],
                    "shift_request_id": request.id,
                    "cast_id": self.cast.id,
                    "approved_date": self.shift_date.isoformat(),
                    "approved_start_time": "18:00",
                    "approved_end_time": "29:00",
                    "approved_room_id": self.room.id,
                    "admin_memo": "深夜承認",
                }],
            },
            format="json",
        )
        self.assertEqual(applied.status_code, 200, applied.data)
        self.assertEqual(applied.data["applied_count"], 1)

        request.refresh_from_db()
        self.assertEqual(request.approved_end_day_offset, 1)
        self.assertEqual(
            ShiftAssignment.objects.get(cast=self.cast).end_day_offset,
            1,
        )
