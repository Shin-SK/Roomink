from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core import test_sales_allocation as fixtures
from core.models import Cast, CastDailyCheckout, Course, DailySettlement, Discount, NominationFee, Option, OrderAccountingCorrection, SmsLog, Store, UserProfile


@override_settings(SMS_DUMMY_MODE=True)
class CompletedAccountingCorrectionTest(TestCase):
    setUp = fixtures.SalesAllocationTest.setUp

    def correct(self, **overrides):
        self.order.refresh_from_db()
        body = {"reason": "割引の入力漏れを訂正", "expected_updated_at": self.order.updated_at.isoformat()}
        body.update(overrides)
        return self.manager_client.post(f"/api/orders/{self.order.pk}/correct-accounting/", body, format="json")

    def discount(self, store=None):
        return Discount.objects.create(store=store or self.store, name="2000円割引", value=2000)

    @patch("core.views.timezone.now", return_value=datetime(2026, 10, 2, 20, tzinfo=ZoneInfo("Asia/Tokyo")))
    def test_full_correction_recalculates_submitted_pay_and_keeps_cash(self, _now):
        self.store.nomination_fullback_enabled = True
        self.store.save()
        self.cast.option_back_rate = 50
        self.cast.save()
        self.assertEqual(self.cast_client.post("/api/cast/checkout/", {"room_cash_taken_amount": 5000}, format="json").status_code, 201)
        course = Course.objects.create(store=self.store, name="90分", duration=90, price=30000)
        option = Option.objects.create(store=self.store, name="追加", price=2000)
        nomination = NominationFee.objects.create(store=self.store, name="本指名", price=3000)
        response = self.correct(course=course.pk, options=[option.pk], nomination_fee=nomination.pk, payment_method="CARD", card_include_options=True)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["total_price"], 35000)
        self.assertEqual(response.data["end_time_extended"], "19:30")
        checkout = CastDailyCheckout.objects.get()
        self.assertEqual(checkout.estimated_pay, 25000)
        self.assertEqual(checkout.course_sales, 30000)
        self.assertEqual(checkout.options_sales, 2000)
        self.assertEqual(checkout.total_sales, 35000)
        self.assertEqual(checkout.customer_payment_total, 38500)
        self.assertEqual(checkout.room_cash_taken_amount, 5000)
        self.assertEqual(checkout.expense_snapshots.get().amount, 5000)
        self.assertEqual(response.data["status"], "DONE")
        self.assertEqual(OrderAccountingCorrection.objects.get().after["option_ids"], [option.pk])
        self.assertFalse(SmsLog.objects.exists())

    @patch("core.views.timezone.now", return_value=datetime(2026, 10, 2, 20, tzinfo=ZoneInfo("Asia/Tokyo")))
    def test_cast_move_updates_both_submitted_checkouts(self, _now):
        self.assertEqual(self.cast_client.post("/api/cast/checkout/", {"room_cash_taken_amount": 5000}, format="json").status_code, 201)
        other = Cast.objects.create(store=self.store, name="別担当", course_back_rate=60)
        target = CastDailyCheckout.objects.create(store=self.store, cast=other, date=self.day, room_cash_taken_amount=1000)
        response = self.correct(cast=other.pk)
        self.assertEqual(response.status_code, 200, response.data)
        source = CastDailyCheckout.objects.get(cast=self.cast)
        target.refresh_from_db()
        self.assertEqual((source.done_count, source.total_sales, source.estimated_pay), (0, 0, 0))
        self.assertEqual(source.room_cash_taken_amount, 5000)
        self.assertEqual((target.done_count, target.total_sales, target.estimated_pay), (1, 24000, 12000))
        self.assertEqual(target.room_cash_taken_amount, 1000)
        self.assertEqual(target.status, "SUBMITTED")

    def test_date_move_checks_both_days_and_records_notes_only_changes(self):
        DailySettlement.objects.create(store=self.store, date="2026-10-03", status="LOCKED")
        response = self.correct(business_date="2026-10-03", start_time_extended="18:00", end_time_extended="19:00")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(self.correct(memo="訂正メモ").status_code, 200)
        audit = OrderAccountingCorrection.objects.get()
        self.assertNotEqual(audit.before["notes_digest"], audit.after["notes_digest"])
        self.assertNotIn("訂正メモ", str(audit.after))
        self.assertEqual(self.correct(business_date="2026-10-04", start_time_extended="25:00", end_time_extended="26:00").status_code, 200)

    @patch("core.views.timezone.now", return_value=datetime(2026, 10, 2, 20, tzinfo=ZoneInfo("Asia/Tokyo")))
    def test_business_day_move_transfers_totals_without_moving_cash(self, _now):
        self.assertEqual(self.cast_client.post("/api/cast/checkout/", {"room_cash_taken_amount": 5000}, format="json").status_code, 201)
        target = CastDailyCheckout.objects.create(store=self.store, cast=self.cast, date="2026-10-03")
        response = self.correct(business_date="2026-10-03", start_time_extended="25:00", end_time_extended="26:00")
        self.assertEqual(response.status_code, 200, response.data)
        source = CastDailyCheckout.objects.get(cast=self.cast, date=self.day)
        target.refresh_from_db()
        self.assertEqual((source.done_count, source.total_sales, source.estimated_pay), (0, 0, 0))
        self.assertEqual(source.room_cash_taken_amount, 5000)
        self.assertEqual((target.done_count, target.total_sales, target.estimated_pay), (1, 24000, 14000))
        self.assertEqual(target.room_cash_taken_amount, 0)

    @patch("core.views.timezone.now", return_value=datetime(2026, 10, 2, 20, tzinfo=ZoneInfo("Asia/Tokyo")))
    def test_option_removal_and_zero_price_preserve_historical_pay_basis(self, _now):
        from core.models import OrderOption
        option = Option.objects.create(store=self.store, name="削除するOP", price=4000)
        OrderOption.objects.create(order=self.order, option=option)
        self.cast.option_back_rate = 50
        self.cast.save()
        self.assertEqual(self.cast_client.post("/api/cast/checkout/", {}, format="json").status_code, 201)
        checkout = CastDailyCheckout.objects.get()
        checkout.estimated_pay = 17000  # 過去の報酬算定を保持し、訂正差額だけを反映。
        checkout.save()
        response = self.correct(options=[])
        self.assertEqual(response.status_code, 200, response.data)
        checkout.refresh_from_db()
        self.assertEqual(checkout.estimated_pay, 15000)
        self.assertEqual(checkout.options_sales, 0)
        self.assertEqual(self.correct(discount=Discount.objects.create(store=self.store, name="全額割引", value=20000).pk).data["total_price"], 0)

    def test_foreign_masters_and_direct_update_remain_protected(self):
        other = Store.objects.create(name="別店舗")
        course = Course.objects.create(store=other, name="別コース", duration=60, price=20000)
        option = Option.objects.create(store=other, name="別OP", price=2000)
        for body in ({"course": course.pk}, {"options": [option.pk]}, {"status": "CONFIRMED"}, {"customer": self.order.customer_id}):
            self.assertEqual(self.correct(**body).status_code, 400)
        self.assertEqual(self.manager_client.patch(f"/api/orders/{self.order.pk}/", {"memo": "迂回"}, format="json").status_code, 400)

    def test_same_local_time_does_not_create_false_correction(self):
        response = self.correct(business_date=str(self.day), start_time_extended="18:00", end_time_extended="19:00")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(OrderAccountingCorrection.objects.exists())

    def test_cast_completion_still_posts_sales_and_operator_can_correct(self):
        self.order.status = "IN_PROGRESS"
        self.order.save()
        ended = self.cast_client.post(f"/api/cast/orders/{self.order.pk}/complete/")
        self.assertEqual(ended.status_code, 200, ended.data)
        self.assertEqual(ended.data["status"], "DONE")
        response = self.correct(discount=self.discount().pk, extension_duration=30, extension_price=5000)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "DONE")
        self.assertEqual(response.data["total_price"], 27000)
        self.assertEqual(response.data["end_time_extended"], "19:30")
        audit = OrderAccountingCorrection.objects.get()
        self.assertEqual(audit.before["total_price"], 24000)
        self.assertEqual(audit.after["total_price"], 27000)
        self.assertEqual(response.data["accounting_corrections"][0]["reason"], audit.reason)
        self.assertFalse(SmsLog.objects.exists())

    @patch("core.views.timezone.now", return_value=datetime(2026, 10, 2, 20, tzinfo=ZoneInfo("Asia/Tokyo")))
    def test_submitted_checkout_refreshes_without_changing_cash_or_expenses(self, _now):
        submitted = self.cast_client.post("/api/cast/checkout/", {"room_cash_taken_amount": 5000}, format="json")
        self.assertEqual(submitted.status_code, 201, submitted.data)
        checkout = CastDailyCheckout.objects.get()
        checkout.status = "REVIEWED"
        checkout.reviewed_at = _now.return_value
        checkout.save()
        before_expenses = list(checkout.expense_snapshots.values_list("name", "amount"))
        response = self.correct(discount=self.discount().pk)
        self.assertEqual(response.status_code, 200, response.data)
        checkout.refresh_from_db()
        self.assertEqual(checkout.total_sales, 22000)
        self.assertEqual(checkout.customer_payment_total, 22000)
        self.assertEqual(checkout.net_sales_after_payment_fee, 22000)
        self.assertEqual(checkout.estimated_pay, 14000)
        self.assertEqual(checkout.room_cash_taken_amount, 5000)
        self.assertEqual(checkout.actual_take_home_amount, 5000)
        self.assertEqual(checkout.status, "SUBMITTED")
        self.assertIsNone(checkout.reviewed_at)
        self.assertEqual(list(checkout.expense_snapshots.values_list("name", "amount")), before_expenses)
        self.assertEqual(OrderAccountingCorrection.objects.get().checkout_id, checkout.pk)

    @patch("core.views.timezone.now", return_value=datetime(2026, 10, 2, 20, tzinfo=ZoneInfo("Asia/Tokyo")))
    def test_card_surcharge_delta_keeps_submitted_snapshot_consistent(self, _now):
        self.order.payment_method = "CARD"
        self.order.card_payment_confirmed_at = _now.return_value
        self.order.save()
        submitted = self.cast_client.post("/api/cast/checkout/", {}, format="json")
        self.assertEqual(submitted.status_code, 201, submitted.data)
        response = self.correct(discount=self.discount().pk)
        self.assertEqual(response.status_code, 200, response.data)
        checkout = CastDailyCheckout.objects.get()
        self.assertEqual(checkout.total_sales, 22000)
        self.assertEqual(checkout.customer_payment_surcharge, 1800)
        self.assertEqual(checkout.customer_payment_total, 23800)
        self.assertEqual(checkout.net_sales_after_payment_fee, 23800)

    def test_locked_day_cannot_be_corrected_and_creates_no_audit(self):
        DailySettlement.objects.create(store=self.store, date=self.day, status="LOCKED")
        response = self.correct(discount=self.discount().pk)
        self.assertEqual(response.status_code, 400, response.data)
        self.order.refresh_from_db()
        self.assertEqual(self.order.total_price, 24000)
        self.assertFalse(OrderAccountingCorrection.objects.exists())

    def test_preexisting_stale_checkout_is_not_silently_changed(self):
        CastDailyCheckout.objects.create(store=self.store, cast=self.cast, date=self.day, total_sales=0)
        response = self.correct(extension_duration=30, extension_price=5000)
        self.assertEqual(response.status_code, 400, response.data)
        self.order.refresh_from_db()
        self.assertEqual(self.order.total_price, 24000)
        self.assertEqual(CastDailyCheckout.objects.get().total_sales, 0)
        self.assertFalse(OrderAccountingCorrection.objects.exists())

    def test_reason_scope_and_foreign_masters_are_validated(self):
        self.assertEqual(self.manager_client.post(f"/api/orders/{self.order.pk}/correct-accounting/", [], format="json").status_code, 400)
        foreign = self.discount(Store.objects.create(name="他店舗"))
        for body in ({"reason": ""}, {"course": self.order.course_id}, {"discount": foreign.pk}, {"extension_duration": 7}, {}):
            response = self.correct(**body)
            self.assertEqual(response.status_code, 400, response.data)
        self.order.status = "CANCELLED"
        self.order.save()
        self.assertEqual(self.correct(discount=self.discount().pk).status_code, 400)
        self.assertFalse(OrderAccountingCorrection.objects.exists())

    def test_stale_retry_is_rejected_without_double_updating(self):
        timestamp = self.order.updated_at.isoformat()
        response = self.correct(discount=self.discount().pk)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.correct(expected_updated_at=timestamp, discount=None).status_code, 409)
        self.assertEqual(OrderAccountingCorrection.objects.count(), 1)
        self.order.refresh_from_db()
        self.assertEqual(self.order.total_price, 22000)

    def test_cast_customer_and_foreign_operator_cannot_correct(self):
        url = f"/api/orders/{self.order.pk}/correct-accounting/"
        body = {"reason": "訂正", "expected_updated_at": self.order.updated_at.isoformat(), "discount": self.discount().pk}
        self.assertEqual(self.cast_client.post(url, body, format="json").status_code, 403)
        other = Store.objects.create(name="他店舗")
        user = get_user_model().objects.create_user("foreign-correction-manager")
        UserProfile.objects.create(store=other, user=user, role="manager")
        client = APIClient()
        client.force_authenticate(user)
        self.assertEqual(client.post(url, body, format="json").status_code, 404)
        customer_user = get_user_model().objects.create_user("correction-customer")
        self.order.customer.user = customer_user
        self.order.customer.save()
        client.force_authenticate(customer_user)
        self.assertEqual(client.post(url, body, format="json").status_code, 403)

    @patch("core.views.timezone.now", return_value=datetime(2026, 10, 2, 20, tzinfo=ZoneInfo("Asia/Tokyo")))
    def test_staff_can_correct_today_but_cannot_move_booking(self, _now):
        staff = get_user_model().objects.create_user("correction-staff")
        UserProfile.objects.create(store=self.store, user=staff, role="staff")
        client = APIClient()
        client.force_authenticate(staff)
        response = client.post(f"/api/orders/{self.order.pk}/correct-accounting/", {
            "reason": "店舗で入力漏れ確認", "expected_updated_at": self.order.updated_at.isoformat(), "discount": self.discount().pk,
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["total_price"], 22000)
        self.assertEqual(OrderAccountingCorrection.objects.get().corrected_by_id, staff.pk)
