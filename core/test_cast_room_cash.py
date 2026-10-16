import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core import test_sales_allocation as fixtures
from core.models import Cast, CastDailyCheckout, Room, RoomCashCheckpoint, ShiftAssignment, Store, UserProfile


@patch("core.views.timezone.now", return_value=datetime(2026, 10, 2, 20, tzinfo=ZoneInfo("Asia/Tokyo")))
class CastRoomCashTests(TestCase):
    setUp = fixtures.SalesAllocationTest.setUp
    url = "/api/cast/room-cash/"

    def get_row(self):
        response = self.cast_client.get(self.url)
        self.assertEqual(response.status_code, 200, response.data)
        return response.data["rooms"][0]

    def count(self, **overrides):
        rows = self.cast_client.get(self.url).data["rooms"]
        row = next((item for item in rows if item["room"] == overrides.get("room", self.order.room_id)), rows[0])
        payload = {"room": self.order.room_id, "date": self.day.isoformat(), "actual_cash_amount": 26000,
                   "expected_revision": row["revision"], "request_id": str(uuid.uuid4()), **overrides}
        return self.cast_client.post(self.url, payload, format="json"), payload

    def test_personal_dto_shows_room_and_only_own_settlement(self, _now):
        other = Cast.objects.create(store=self.store, name="他の人の秘密報酬")
        CastDailyCheckout.objects.create(store=self.store, cast=other, date=self.day,
                                         room=self.order.room, estimated_pay=987654)
        CastDailyCheckout.objects.create(store=self.store, cast=other, date=self.day - timedelta(days=1),
                                         room=self.order.room, estimated_pay=123456, status="RETURNED")
        row = self.get_row()
        self.assertEqual(row["room"], self.order.room_id)
        self.assertEqual(row["settlement"]["compensation_amount"], 9000)
        self.assertIsNone(row["expected_cash_amount"])
        for key in ("casts", "history", "memo", "source_cash_amount", "cash_sales_amount", "room_cash_taken_amount", "opening_cash_amount"):
            self.assertNotIn(key, row)
        serialized = json.dumps(row, ensure_ascii=False)
        self.assertNotIn(other.name, serialized)
        self.assertNotIn("987654", serialized)
        self.assertNotIn("123456", serialized)

    def test_count_creates_shared_anchor_without_changing_payroll(self, _now):
        response, _ = self.count()
        self.assertEqual(response.status_code, 200, response.data)
        row = response.data["rooms"][0]
        self.assertEqual(row["expected_cash_amount"], 26000)
        self.assertEqual(row["settlement"]["compensation_amount"], 9000)
        self.assertEqual(row["settlement"]["shortage_amount"], 0)
        checkpoint = RoomCashCheckpoint.objects.get()
        self.assertEqual(checkpoint.counted_by_id, self.cast.user_id)
        self.assertFalse(CastDailyCheckout.objects.filter(cast=self.cast).exists())
        manager = self.manager_client.get("/api/cast-checkouts/room-cash/?date=2026-10-02")
        self.assertEqual(manager.data["rooms"][0]["expected_cash_amount"], 26000)

    def test_other_roles_and_anonymous_cannot_use_cast_api(self, _now):
        self.assertEqual(self.manager_client.get(self.url).status_code, 403)
        user = get_user_model().objects.create_user("cast-cash-staff")
        UserProfile.objects.create(user=user, store=self.store, role="staff")
        client = APIClient()
        client.force_authenticate(user)
        self.assertEqual(client.get(self.url).status_code, 403)
        self.assertIn(APIClient().get(self.url).status_code, (401, 403))

    def test_outside_assigned_room_and_other_store_are_denied(self, _now):
        unassigned = Room.objects.create(store=self.store, name="担当外")
        other_store = Store.objects.create(name="他店")
        foreign_room = Room.objects.create(store=other_store, name="他店の秘密ルーム")
        for room in (unassigned, foreign_room):
            self.assertEqual(self.cast_client.get(self.url, {"room": room.pk}).status_code, 403)
            response, _ = self.count(room=room.pk)
            self.assertEqual(response.status_code, 403)
        self.assertEqual(RoomCashCheckpoint.objects.count(), 0)

    def test_past_future_and_other_person_parameters_rejected(self, _now):
        for day in (self.day - timedelta(days=1), self.day + timedelta(days=1)):
            self.assertEqual(self.cast_client.get(self.url, {"date": day.isoformat()}).status_code, 400)
            response, _ = self.count(date=day.isoformat())
            self.assertEqual(response.status_code, 400)
        for key in ("cast", "cast_id", "store", "store_id", "history"):
            self.assertEqual(self.cast_client.get(self.url, {key: 123}).status_code, 400)
            response, _ = self.count(**{key: 123})
            self.assertEqual(response.status_code, 400)

    def test_same_request_retry_and_stale_revision(self, _now):
        response, payload = self.count()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.cast_client.post(self.url, payload, format="json").status_code, 200)
        self.assertEqual(RoomCashCheckpoint.objects.count(), 1)
        self.assertEqual(self.cast_client.post(self.url, {**payload, "actual_cash_amount": 1}, format="json").status_code, 409)
        self.assertEqual(self.cast_client.post(self.url, {**payload, "request_id": str(uuid.uuid4())}, format="json").status_code, 409)

    def test_source_change_rejects_count_with_old_revision(self, _now):
        row = self.get_row()
        self.order.total_price += 1000
        self.order.save(update_fields=["total_price"])
        response, _ = self.count(expected_revision=row["revision"])
        self.assertEqual(response.status_code, 409)
        self.assertEqual(RoomCashCheckpoint.objects.count(), 0)

    def test_multiple_rooms_require_explicit_selection(self, _now):
        second = Room.objects.create(store=self.store, name="別の担当ルーム")
        self.order.room = second
        self.order.save(update_fields=["room"])
        response, _ = self.count(room=second.pk)
        self.assertEqual(response.status_code, 200)
        initial = self.cast_client.get(self.url)
        self.assertTrue(initial.data["requires_room_selection"])
        self.assertIsNone(initial.data["selected_room"])
        self.assertEqual(len(initial.data["rooms"]), 2)
        for row in initial.data["rooms"]:
            self.assertIsNone(row["settlement"]["suggested_take_amount"])
        selected = self.cast_client.get(self.url, {"room": second.pk})
        self.assertFalse(selected.data["requires_room_selection"])
        self.assertEqual(selected.data["selected_room"], second.pk)
        self.assertEqual(selected.data["rooms"][0]["settlement"]["suggested_take_amount"], 9000)

    def test_absent_shift_without_done_order_does_not_grant_access(self, _now):
        self.order.status = "CANCELLED"
        self.order.save(update_fields=["status"])
        ShiftAssignment.objects.filter(cast=self.cast).update(is_absent=True)
        response = self.cast_client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["rooms"], [])
        self.assertEqual(self.cast_client.get(self.url, {"room": self.order.room_id}).status_code, 403)
        self.order.status = "DONE"
        self.order.save(update_fields=["status"])
        self.assertEqual(len(self.cast_client.get(self.url).data["rooms"]), 1)

    def test_manager_memo_and_count_history_are_not_disclosed(self, _now):
        row = self.get_row()
        response = self.manager_client.post("/api/cast-checkouts/room-cash/", {
            "date": self.day.isoformat(), "room": self.order.room_id,
            "actual_cash_amount": 26000, "memo": "管理者だけが見る秘密メモ",
            "expected_revision": row["revision"], "request_id": str(uuid.uuid4()),
        }, format="json")
        self.assertEqual(response.status_code, 200)
        serialized = json.dumps(self.cast_client.get(self.url).data, ensure_ascii=False)
        self.assertNotIn("秘密メモ", serialized)
        self.assertNotIn('"history"', serialized)
        self.assertNotIn('"counted_by"', serialized)

    def test_checkout_room_alone_does_not_grant_access(self, _now):
        outsider = Room.objects.create(store=self.store, name="過去の精算ルーム")
        CastDailyCheckout.objects.create(store=self.store, cast=self.cast, date=self.day, room=outsider)
        response = self.cast_client.get(self.url)
        self.assertEqual([row["room"] for row in response.data["rooms"]], [self.order.room_id])
        self.assertEqual(self.cast_client.get(self.url, {"room": outsider.pk}).status_code, 403)

    def test_profile_store_must_match_cast_store(self, _now):
        other_store = Store.objects.create(name="プロフィール店舗不一致")
        profile = UserProfile.objects.get(user=self.cast.user)
        profile.store = other_store
        with patch("core.views.get_request_profile", return_value=profile):
            self.assertEqual(self.cast_client.get(self.url).status_code, 403)
