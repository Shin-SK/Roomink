import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from core.models import CastDailyCheckout, Order, Room, RoomCashCheckpoint, RoomCashCount, RoomCashMovement, Store, UserProfile
import core.test_sales_allocation as allocation_fixture


@patch("core.views.timezone.now", return_value=datetime(2026, 10, 2, 20, tzinfo=ZoneInfo("Asia/Tokyo")))
class RoomCashProjectionTests(TestCase):
    def setUp(self):
        allocation_fixture.SalesAllocationTest.setUp(self)
        self.room = self.order.room
        self.url = "/api/cast-checkouts/room-cash/?date=2026-10-02"

    def summary(self):
        response = self.manager_client.get(self.url)
        self.assertEqual(response.status_code, 200, response.data)
        return next(item for item in response.data["rooms"] if item["room"] == self.room.pk)

    def count(self, amount=26000, **overrides):
        row = self.summary()
        payload = {"date": self.day.isoformat(), "room": self.room.pk, "actual_cash_amount": amount,
                   "memo": "確認済", "expected_revision": row["revision"], "request_id": str(uuid.uuid4()), **overrides}
        return self.manager_client.post("/api/cast-checkouts/room-cash/", payload, format="json"), payload

    def test_unknown_is_not_zero_and_first_count_anchors_current_cash(self, _now):
        row = self.summary()
        self.assertFalse(row["balance_known"])
        self.assertIsNone(row["expected_cash_amount"])
        self.assertEqual(row["cash_sales_amount"], 24000)
        self.assertIsNone(row["casts"][0]["shortage_amount"])
        response, _ = self.count()
        self.assertEqual(response.status_code, 200, response.data)
        row = self.summary()
        self.assertEqual(row["expected_cash_amount"], 26000)
        self.assertIsNone(row["difference_amount"])
        self.assertEqual(RoomCashCount.objects.count(), 0)
        self.assertTrue(any(item["kind"] == "COUNT" for item in row["history"]))

    def test_31000_due_26000_cash_and_handover_then_5000_remaining(self, _now):
        checkout = CastDailyCheckout.objects.create(store=self.store, cast=self.cast, date=self.day,
                                                   room=self.room, estimated_pay=31000)
        self.assertEqual(self.count()[0].status_code, 200)
        cast_row = self.summary()["casts"][0]
        self.assertEqual(cast_row["suggested_take_amount"], 26000)
        self.assertEqual(cast_row["projected_room_balance"], 0)
        self.assertEqual(cast_row["shortage_amount"], 5000)
        response = self.manager_client.patch(f"/api/cast-checkouts/{checkout.pk}/cash-settlement/",
                                            {"room_cash_taken_amount": 26000}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        row = self.summary()
        self.assertEqual(row["expected_cash_amount"], 0)
        self.assertEqual(row["casts"][0]["remaining_receivable_amount"], 5000)
        self.assertEqual(row["casts"][0]["shortage_amount"], 5000)

    def test_card_cash_options_and_all_intervening_days(self, _now):
        self.assertEqual(self.count()[0].status_code, 200)
        card = Order.objects.get(pk=self.order.pk)
        card.pk = None
        card.start -= timedelta(days=1)
        card.end -= timedelta(days=1)
        card.payment_method = Order.PaymentMethod.CARD
        card.card_include_options = False
        card.save()
        self.assertEqual(self.summary()["expected_cash_amount"], 30000)
        card.card_include_options = True
        card.save(update_fields=["card_include_options"])
        self.assertEqual(self.summary()["expected_cash_amount"], 26000)
        self.assertTrue(self.summary()["requires_confirmation"])

    def test_legacy_closing_count_includes_uncounted_days(self, _now):
        RoomCashCount.objects.create(store=self.store, room=self.room, date=self.day - timedelta(days=3), actual_cash_amount=1000)
        earlier = Order.objects.get(pk=self.order.pk)
        earlier.pk = None
        earlier.start -= timedelta(days=1)
        earlier.end -= timedelta(days=1)
        earlier.save()
        self.assertEqual(self.summary()["expected_cash_amount"], 49000)

    def test_return_review_status_and_office_payment_do_not_move_room_cash(self, _now):
        checkout = CastDailyCheckout.objects.create(store=self.store, cast=self.cast, date=self.day,
                                                   room=self.room, estimated_pay=31000, room_cash_taken_amount=26000)
        self.assertEqual(self.count(amount=1000)[0].status_code, 200)
        movement_count = RoomCashMovement.objects.count()
        response = self.manager_client.post(f"/api/cast-checkouts/{checkout.pk}/return_to_cast/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.summary()["expected_cash_amount"], 1000)
        checkout.refresh_from_db()
        checkout.office_cash_paid_amount = 1000
        checkout.save(update_fields=["office_cash_paid_amount"])
        self.assertEqual(self.summary()["expected_cash_amount"], 1000)
        self.assertEqual(RoomCashMovement.objects.count(), movement_count)

    def test_count_revision_and_idempotency_protect_retry(self, _now):
        response, payload = self.count()
        self.assertEqual(response.status_code, 200)
        repeated = self.manager_client.post("/api/cast-checkouts/room-cash/", payload, format="json")
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(RoomCashCheckpoint.objects.count(), 1)
        changed = self.manager_client.post("/api/cast-checkouts/room-cash/", {**payload, "actual_cash_amount": 123}, format="json")
        self.assertEqual(changed.status_code, 409)
        stale = self.manager_client.post("/api/cast-checkouts/room-cash/", {**payload, "request_id": str(uuid.uuid4())}, format="json")
        self.assertEqual(stale.status_code, 409)
        row = self.summary()
        self.order.total_price += 1000
        self.order.save(update_fields=["total_price"])
        stale_source, _ = self.count(expected_revision=row["revision"])
        self.assertEqual(stale_source.status_code, 409)

    def test_second_count_fixes_difference_at_the_instant_of_count(self, _now):
        self.count()
        self.order.total_price += 1000
        self.order.save(update_fields=["total_price"])
        response, _ = self.count(amount=26500)
        self.assertEqual(response.status_code, 200)
        row = self.summary()
        self.assertEqual(row["expected_cash_amount"], 26500)
        self.assertEqual(row["difference_amount"], -500)
        self.order.total_price += 1000
        self.order.save(update_fields=["total_price"])
        self.assertEqual(self.summary()["expected_cash_amount"], 27500)
        self.assertEqual(self.summary()["difference_amount"], -500)

    def test_bulk_source_correction_still_updates_projection_and_warns(self, _now):
        self.count()
        Order.objects.filter(pk=self.order.pk).update(total_price=25000)
        row = self.summary()
        self.assertEqual(row["expected_cash_amount"], 27000)
        self.assertTrue(row["requires_confirmation"])

    def test_multiple_rooms_does_not_duplicate_a_payment_suggestion(self, _now):
        second = Room.objects.create(store=self.store, name="102")
        self.order.room = second
        self.order.save(update_fields=["room"])
        self.count()
        row = self.summary()
        self.assertTrue(row["casts"][0]["ambiguous_room"])
        self.assertIsNone(row["casts"][0]["suggested_take_amount"])

    def test_record_failure_rolls_back_source_and_event(self, _now):
        before = self.order.total_price
        with patch.object(RoomCashMovement.objects, "create", side_effect=RuntimeError("audit failed")):
            self.order.total_price += 1000
            with self.assertRaises(RuntimeError):
                self.order.save(update_fields=["total_price"])
        self.order.refresh_from_db()
        self.assertEqual(self.order.total_price, before)

    def test_permissions_store_boundary_and_past_count_denial(self, _now):
        self.assertEqual(self.cast_client.get(self.url).status_code, 403)
        user = get_user_model().objects.create_user("cash-staff")
        UserProfile.objects.create(user=user, store=self.store, role="staff")
        client = APIClient()
        client.force_authenticate(user)
        self.assertEqual(client.get(self.url).status_code, 403)
        other_store = Store.objects.create(name="別店舗")
        other_room = Room.objects.create(store=other_store, name="別室")
        response, _ = self.count(room=other_room.pk)
        self.assertEqual(response.status_code, 400)
        response, _ = self.count(date=(self.day - timedelta(days=1)).isoformat())
        self.assertEqual(response.status_code, 400)

    def test_count_rejects_noninteger_and_out_of_range_amount(self, _now):
        for amount in (True, 100.5, -1, 2147483648, "1.5", None):
            with self.subTest(amount=amount):
                response, _ = self.count(amount=amount)
                self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(RoomCashCheckpoint.objects.count(), 0)

    def test_cash_handover_audit_records_the_operator(self, _now):
        checkout = CastDailyCheckout.objects.create(store=self.store, cast=self.cast, date=self.day,
                                                   room=self.room, estimated_pay=31000)
        response = self.manager_client.patch(f"/api/cast-checkouts/{checkout.pk}/cash-settlement/",
                                            {"room_cash_taken_amount": 1000}, format="json")
        self.assertEqual(response.status_code, 200)
        movement = RoomCashMovement.objects.filter(source_type="checkout").latest("pk")
        self.assertEqual(movement.recorded_by_id, self.manager_client.handler._force_user.pk)

    def test_business_day_boundary_uses_store_date(self, _now):
        _now.return_value = datetime(2026, 10, 3, 4, 59, tzinfo=ZoneInfo("Asia/Tokyo"))
        self.assertEqual(self.count()[0].status_code, 200)
        _now.return_value = datetime(2026, 10, 3, 5, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
        self.assertFalse(self.summary()["can_count"])
        self.assertEqual(self.count()[0].status_code, 400)

    def test_unassigned_physical_handover_is_flagged_and_not_guessed(self, _now):
        self.count()
        CastDailyCheckout.objects.create(store=self.store, cast=self.cast, date=self.day,
                                         room=None, estimated_pay=31000, room_cash_taken_amount=1000)
        row = self.summary()
        self.assertTrue(row["requires_confirmation"])
        self.assertIsNone(row["casts"][0]["suggested_take_amount"])

    def test_prior_returned_checkout_suppresses_only_that_casts_projection(self, _now):
        self.count()
        CastDailyCheckout.objects.create(store=self.store, cast=self.cast,
                                         date=self.day - timedelta(days=1), room=self.room,
                                         status=CastDailyCheckout.Status.RETURNED, estimated_pay=5000)
        row = self.summary()
        self.assertTrue(row["casts"][0]["settlement_pending"])
        self.assertIsNone(row["casts"][0]["suggested_take_amount"])
        self.assertIsNone(row["casts"][0]["shortage_amount"])
        self.assertTrue(any("差戻し中" in warning for warning in row["warnings"]))


@skipUnless(connection.vendor == "postgresql", "PostgreSQL row locks are required")
class RoomCashConcurrencyTests(TransactionTestCase):
    setUp = allocation_fixture.SalesAllocationTest.setUp

    def _race(self, same_request):
        actor = self.manager_client.handler._force_user
        row = self.manager_client.get("/api/cast-checkouts/room-cash/?date=2026-10-02").data["rooms"][0]
        barrier = Barrier(2)
        key = str(uuid.uuid4())

        def count():
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(actor)
                barrier.wait(timeout=10)
                return client.post("/api/cast-checkouts/room-cash/", {
                    "date": self.day.isoformat(), "room": self.order.room_id, "actual_cash_amount": 26000,
                    "request_id": key if same_request else str(uuid.uuid4()), "expected_revision": row["revision"],
                }, format="json").status_code
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(count) for _ in range(2)]
            statuses = sorted(future.result(timeout=30) for future in futures)
        self.assertEqual(statuses, [200, 200] if same_request else [200, 409])
        self.assertEqual(RoomCashCheckpoint.objects.count(), 1)

    @patch("core.views.timezone.now", return_value=datetime(2026, 10, 2, 20, tzinfo=ZoneInfo("Asia/Tokyo")))
    def test_simultaneous_different_counts_have_one_winner(self, _now):
        self._race(same_request=False)

    @patch("core.views.timezone.now", return_value=datetime(2026, 10, 2, 20, tzinfo=ZoneInfo("Asia/Tokyo")))
    def test_simultaneous_retry_does_not_duplicate_count(self, _now):
        self._race(same_request=True)
