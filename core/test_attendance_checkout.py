from datetime import date, datetime, time, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Cast, CastDailyCheckout, DailySettlement, ShiftAssignment, ShiftAttendanceEvent, Store, UserProfile
from core import test_sales_business_datetime

TOKYO = ZoneInfo("Asia/Tokyo")
NOW = datetime(2026, 8, 1, 10, tzinfo=TOKYO)


@patch("django.utils.timezone.now", return_value=NOW)
class AttendanceCheckoutTest(TestCase):
    setUp = test_sales_business_datetime.SalesBusinessDateTimeTest.setUp

    def shift(self):
        return ShiftAssignment.objects.get(cast=self.cast, date=self.business_date)

    def stamp_in(self):
        shift = self.shift()
        shift.clocked_in_at = datetime(2026, 7, 31, 18, tzinfo=TOKYO)
        shift.save(update_fields=["clocked_in_at"])
        return shift

    def punch(self, shift, action):
        return self.cast_client.post("/api/cast/attendance/", {"shift_id": shift.pk, "action": action}, format="json")

    def correction(self, shift, **values):
        return self.manager_client.post("/api/op/attendance/", {
            "shift_id": shift.pk, "clocked_in_at": shift.clocked_in_at.isoformat() if shift.clocked_in_at else None,
            "clocked_out_at": datetime(2026, 8, 1, 5, tzinfo=TOKYO).isoformat(),
            "expected": {"clocked_in_at": shift.clocked_in_at.isoformat() if shift.clocked_in_at else None,
                         "clocked_out_at": shift.clocked_out_at.isoformat() if shift.clocked_out_at else None},
            "reason": "退勤を押し忘れたため、本人確認のうえ訂正", **values,
        }, format="json")

    def test_clock_out_after_five_preserves_shift_and_is_idempotent(self, _now):
        shift = self.stamp_in()
        result = self.punch(shift, "clock_out")
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data["date"], "2026-07-31")
        self.assertIn("退勤が予定と1時間以上ずれています", result.data["alerts"])
        self.assertEqual(self.punch(shift, "clock_out").status_code, 200)
        shift.refresh_from_db()
        self.assertEqual(shift.clocked_out_at, NOW)
        self.assertEqual(ShiftAttendanceEvent.objects.filter(shift=shift).count(), 1)
        self.assertFalse(CastDailyCheckout.objects.exists())

    def test_open_shift_survives_multiple_business_days(self, _now):
        self.stamp_in()
        with patch("django.utils.timezone.now", return_value=NOW + timedelta(days=4)):
            result = self.cast_client.get("/api/cast/attendance/")
        self.assertEqual(len(result.data["shifts"]), 1)
        self.assertIn("未退勤", result.data["shifts"][0]["alerts"])

    def test_prior_open_shift_does_not_block_current_check_in(self, _now):
        self.stamp_in()
        today_shift = ShiftAssignment.objects.create(store=self.store, cast=self.cast, date=NOW.date(),
                                                     start_time=time(9), end_time=time(18))
        result = self.punch(today_shift, "clock_in")
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(self.punch(today_shift, "clock_in").status_code, 200)
        self.assertEqual(today_shift.attendance_events.count(), 1)
        self.assertIsNone(self.shift().clocked_out_at)

    def test_today_check_in_can_record_early_arrival(self, _now):
        shift = ShiftAssignment.objects.create(store=self.store, cast=self.cast, date=NOW.date(),
                                                start_time=time(11), end_time=time(18))
        result = self.punch(shift, "clock_in")
        self.assertEqual(result.status_code, 200, result.data)
        shift.refresh_from_db()
        self.assertEqual(shift.clocked_in_at, NOW)

    def test_old_client_must_not_submit_previous_day_amount_as_today(self, _now):
        self.assertEqual(self.cast_client.get("/api/cast/checkout/").data["date"], "2026-07-31")
        result = self.cast_client.post("/api/cast/checkout/", {"room_cash_taken_amount": 1000}, format="json")
        self.assertEqual(result.status_code, 400, result.data)
        self.assertFalse(CastDailyCheckout.objects.exists())

    def test_no_arbitrary_punch_time_or_future_shift(self, _now):
        shift = self.shift()
        self.assertEqual(self.punch(shift, "clock_out").status_code, 400)
        self.assertEqual(self.punch(shift, "clock_in").status_code, 400)
        result = self.cast_client.post("/api/cast/attendance/", {"shift_id": shift.pk, "action": "clock_out", "clocked_out_at": NOW.isoformat()}, format="json")
        self.assertEqual(result.status_code, 400)

    def test_correction_requires_reason_preserves_original_and_checks_conflict(self, _now):
        shift = self.stamp_in()
        self.punch(shift, "clock_out")
        shift.refresh_from_db()
        self.assertEqual(self.correction(shift, reason="").status_code, 400)
        self.assertEqual(self.correction(shift, expected={"clocked_in_at": None, "clocked_out_at": None}).status_code, 409)
        result = self.correction(shift)
        self.assertEqual(result.status_code, 200, result.data)
        events = list(shift.attendance_events.all())
        self.assertEqual(len(events), 2)
        self.assertEqual(datetime.fromisoformat(events[0].before["clocked_out_at"]), NOW)
        self.assertEqual(events[0].recorded_at, NOW)
        self.assertEqual(events[0].recorded_by_id, self.manager_client.handler._force_user.pk)
        self.assertEqual(self.correction(shift).status_code, 409)

    def test_invalid_corrections_do_not_write(self, _now):
        shift = self.stamp_in()
        for values in [{"clocked_out_at": "2026-07-31T17:00:00+09:00"},
                       {"clocked_out_at": (NOW + timedelta(hours=1)).isoformat()},
                       {"clocked_in_at": None}]:
            with self.subTest(values=values):
                self.assertEqual(self.correction(shift, **values).status_code, 400)
        self.assertFalse(ShiftAttendanceEvent.objects.exists())

    def test_past_checkout_uses_own_day_and_actual_submission_time(self, _now):
        result = self.cast_client.get("/api/cast/checkout/")
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data["date"], "2026-07-31")
        self.assertEqual(result.data["current_business_date"], "2026-08-01")
        result = self.cast_client.post("/api/cast/checkout/", {"date": "2026-07-31", "room_cash_taken_amount": 1000}, format="json")
        self.assertEqual(result.status_code, 201, result.data)
        checkout = CastDailyCheckout.objects.get()
        self.assertEqual(checkout.date, self.business_date)
        self.assertEqual(checkout.submitted_at, NOW)
        self.assertEqual(checkout.estimated_pay, 5000)
        self.assertEqual(checkout.total_sales, 10000)
        self.assertEqual(self.cast_client.post("/api/cast/checkout/", {"date": "2026-07-31"}, format="json").status_code, 400)

    def test_midnight_and_five_boundary_do_not_change_explicit_checkout_day(self, _now):
        for hour, minute in [(4, 59), (5, 0), (5, 1), (10, 0)]:
            with self.subTest(hour=hour, minute=minute), patch("django.utils.timezone.now", return_value=NOW.replace(hour=hour, minute=minute)):
                result = self.cast_client.get("/api/cast/checkout/?date=2026-07-31")
                self.assertEqual(result.status_code, 200, result.data)
                self.assertEqual(result.data["estimated_pay"], 5000)
                self.assertEqual(result.data["date"], "2026-07-31")

    def test_date_validation_and_no_other_cast_dates(self, _now):
        for value, expected in [("bad", 400), ("2026-08-02", 403), ("2026-07-30", 403)]:
            self.assertEqual(self.cast_client.get(f"/api/cast/checkout/?date={value}").status_code, expected)
            self.assertEqual(self.cast_client.post("/api/cast/checkout/", {"date": value}, format="json").status_code, expected)

    def test_locked_accounting_denies_checkout_but_allows_attendance(self, _now):
        DailySettlement.objects.create(store=self.store, date=self.business_date, status=DailySettlement.Status.LOCKED)
        result = self.cast_client.get("/api/cast/checkout/?date=2026-07-31")
        self.assertFalse(result.data["can_submit"])
        self.assertTrue(result.data["is_locked"])
        self.assertEqual(self.cast_client.post("/api/cast/checkout/", {"date": "2026-07-31"}, format="json").status_code, 400)
        self.assertEqual(self.punch(self.stamp_in(), "clock_out").status_code, 200)

    def test_zero_order_shift_and_returned_checkout(self, _now):
        self.order.delete()
        result = self.cast_client.post("/api/cast/checkout/", {"date": "2026-07-31"}, format="json")
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(result.data["estimated_pay"], 0)
        checkout = CastDailyCheckout.objects.get()
        checkout.status = CastDailyCheckout.Status.RETURNED
        checkout.save()
        result = self.cast_client.get("/api/cast/checkout/")
        self.assertEqual(result.data["date"], "2026-07-31")
        self.assertTrue(result.data["can_submit"])
        self.assertEqual(self.cast_client.post("/api/cast/checkout/", {"date": "2026-07-31"}, format="json").status_code, 201)

    def test_manager_ordinary_shift_update_cannot_bypass_attendance_audit(self, _now):
        shift = self.stamp_in()
        result = self.manager_client.patch(f"/api/shifts/{shift.pk}/", {"clocked_in_at": None, "clocked_out_at": NOW.isoformat()}, format="json")
        self.assertEqual(result.status_code, 200, result.data)
        shift.refresh_from_db()
        self.assertIsNotNone(shift.clocked_in_at)
        self.assertIsNone(shift.clocked_out_at)
        self.assertEqual(self.manager_client.delete(f"/api/shifts/{shift.pk}/").status_code, 400)
        self.assertEqual(self.manager_client.patch(f"/api/shifts/{shift.pk}/", {"date": "2026-07-30"}, format="json").status_code, 400)

    def test_roles_and_tenant_boundaries(self, _now):
        store = Store.objects.create(name="別店舗")
        user = get_user_model().objects.create_user("attendance_other")
        UserProfile.objects.create(user=user, store=store, role=UserProfile.Role.CAST)
        cast = Cast.objects.create(store=store, user=user, name="別店舗キャスト")
        other = ShiftAssignment.objects.create(store=store, cast=cast, date=self.business_date, start_time=time(18), end_time=time(23))
        self.assertEqual(self.punch(other, "clock_out").status_code, 404)
        self.assertEqual(self.correction(other).status_code, 404)
        for role in [UserProfile.Role.STAFF, UserProfile.Role.CAST]:
            account = get_user_model().objects.create_user(f"attendance_{role}")
            UserProfile.objects.create(user=account, store=self.store, role=role)
            client = APIClient()
            client.force_authenticate(account)
            self.assertEqual(client.get("/api/op/attendance/?date=2026-07-31").status_code, 403)
        self.assertEqual(self.manager_client.get("/api/cast/attendance/").status_code, 403)
        self.assertEqual(APIClient().get("/api/cast/attendance/").status_code, 403)
