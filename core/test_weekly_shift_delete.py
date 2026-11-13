from datetime import date, datetime, time
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from core.models import Cast, ShiftAssignment, ShiftAttendanceEvent, Store, UserProfile
from core import test_sales_business_datetime


class WeeklyShiftDeleteTest(TestCase):
    setUp = test_sales_business_datetime.SalesBusinessDateTimeTest.setUp
    url = "/api/op/shifts/weekly/"

    def shift(self, **overrides):
        values = dict(store=self.store, cast=self.cast, date=date(2026, 7, 30),
                      start_time=time(18), end_time=time(23))
        values.update(overrides)
        return ShiftAssignment.objects.create(**values)

    def delete(self, shifts, client=None, **overrides):
        body = dict(cast=self.cast.pk, week_start="2026-07-27", shift_ids=[s.pk for s in shifts])
        body.update(overrides)
        return (client or self.manager_client).delete(self.url, body, format="json")

    def test_selected_only_deleted_and_retry_does_not_delete_new_shifts(self):
        first = self.shift()
        second = self.shift(date=date(2026, 7, 29))
        kept = self.shift(date=date(2026, 7, 28))
        result = self.delete([first, second])
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data["deleted_count"], 2)
        self.assertTrue(ShiftAssignment.objects.filter(pk=kept.pk).exists())
        replacement = self.shift()
        self.assertEqual(self.delete([first, second]).status_code, 400)
        self.assertTrue(ShiftAssignment.objects.filter(pk=replacement.pk).exists())

    def test_active_overnight_booking_keeps_entire_selection(self):
        self.order.status = "CONFIRMED"
        self.order.save(update_fields=["status"])
        protected = ShiftAssignment.objects.get(cast=self.cast, date=self.business_date)
        allowed = self.shift()
        result = self.delete([allowed, protected])
        self.assertEqual(result.status_code, 400, result.data)
        self.assertEqual(result.data["errors"][0]["date"], "2026-07-31")
        self.assertEqual(ShiftAssignment.objects.filter(pk__in=[allowed.pk, protected.pk]).count(), 2)

    def test_cancelled_booking_does_not_block_deletion(self):
        self.order.status = "CANCELLED"
        self.order.save(update_fields=["status"])
        protected = ShiftAssignment.objects.get(cast=self.cast, date=self.business_date)
        self.assertEqual(self.delete([protected]).status_code, 200)

    def test_punch_and_cleared_punch_history_keep_entire_selection(self):
        allowed = self.shift()
        protected = self.shift(date=date(2026, 7, 29), clocked_in_at=datetime(2026, 7, 29, 18, tzinfo=ZoneInfo("Asia/Tokyo")))
        self.assertEqual(self.delete([allowed, protected]).status_code, 400)
        protected.clocked_in_at = None
        protected.save(update_fields=["clocked_in_at"])
        ShiftAttendanceEvent.objects.create(shift=protected, action="manager_clear")
        self.assertEqual(self.delete([allowed, protected]).status_code, 400)
        self.assertEqual(ShiftAssignment.objects.filter(pk__in=[allowed.pk, protected.pk]).count(), 2)

    def test_other_store_cast_week_missing_and_malformed_ids_keep_selection(self):
        allowed = self.shift()
        other_store = Store.objects.create(name="別店舗")
        other_cast = Cast.objects.create(store=other_store, name="別人")
        other = self.shift(store=other_store, cast=other_cast)
        same_store_other_cast = Cast.objects.create(store=self.store, name="別キャスト")
        wrong_cast_shift = self.shift(cast=same_store_other_cast)
        wrong_week = self.shift(date=date(2026, 8, 3))
        for shift in [other, wrong_cast_shift, wrong_week]:
            self.assertEqual(self.delete([allowed, shift]).status_code, 400)
        for ids in [[], [allowed.pk, allowed.pk], [True], [str(allowed.pk)], [None], [-1], list(range(1, 102)), [999999999]]:
            self.assertEqual(self.delete([], shift_ids=ids).status_code, 400)
        self.assertEqual(self.delete([allowed], cast=other_cast.pk).status_code, 404)
        self.assertTrue(ShiftAssignment.objects.filter(pk=allowed.pk).exists())

    def test_staff_allowed_cast_and_anonymous_denied(self):
        allowed = self.shift()
        self.assertEqual(self.delete([allowed], client=self.cast_client).status_code, 403)
        self.assertIn(self.delete([allowed], client=APIClient()).status_code, [401, 403])
        staff = get_user_model().objects.create_user("weekly_delete_staff")
        UserProfile.objects.create(user=staff, store=self.store, role=UserProfile.Role.STAFF)
        client = APIClient()
        client.force_authenticate(staff)
        self.assertEqual(self.delete([allowed], client=client).status_code, 200)

    def test_weekly_listing_refreshes_and_new_registration_still_works(self):
        allowed = self.shift()
        self.assertEqual(self.delete([allowed]).status_code, 200)
        result = self.manager_client.get(self.url, {"cast": self.cast.pk, "week_start": "2026-07-27"})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["days"][3]["existing_shifts"], [])
        result = self.manager_client.post(self.url, {"cast": self.cast.pk, "week_start": "2026-07-27", "items": [
            {"date": "2026-07-30", "enabled": True, "start_time": "18:00", "end_time": "23:00"},
        ]}, format="json")
        self.assertEqual(result.status_code, 201, result.data)


@skipUnless(connection.vendor == "postgresql", "Row-lock concurrency requires PostgreSQL")
class WeeklyShiftDeleteConcurrencyTest(TransactionTestCase):
    setUp = test_sales_business_datetime.SalesBusinessDateTimeTest.setUp

    def test_booking_transaction_commits_before_deletion_rechecks_protection(self):
        shift = ShiftAssignment.objects.get(cast=self.cast, date=self.business_date)
        manager_id = self.manager_client.handler._force_user.pk
        started = Event()

        def delete_on_separate_connection():
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(get_user_model().objects.get(pk=manager_id))
                started.set()
                return client.delete("/api/op/shifts/weekly/", {
                    "cast": self.cast.pk, "week_start": "2026-07-27", "shift_ids": [shift.pk],
                }, format="json").status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                Store.objects.select_for_update().get(pk=self.store.pk)
                self.order.status = "CONFIRMED"
                self.order.save(update_fields=["status"])
                future = pool.submit(delete_on_separate_connection)
                self.assertTrue(started.wait(timeout=5))
                self.assertFalse(future.done())
            self.assertEqual(future.result(timeout=10), 400)
        self.assertTrue(ShiftAssignment.objects.filter(pk=shift.pk).exists())
