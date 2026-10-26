from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase, TransactionTestCase, override_settings

from core import test_sales_allocation as fixtures
from core.models import CastDailyCheckout, DailySettlement, Order, SmsLog, LineNotificationLog
from core.services.compensation import compensation_total
from core.services.pricing import recalculate_order_total
from core.services.sales import get_sales_cast_detail, get_sales_dashboard
from core.test_migration_helpers import migrate_test_schema
from core.views import _compute_cast_done_sales


@override_settings(SMS_DUMMY_MODE=True)
@patch("core.views.timezone.now", return_value=datetime(2026, 10, 2, 20, tzinfo=ZoneInfo("Asia/Tokyo")))
class ExtensionCompensationTest(TestCase):
    def setUp(self):
        fixtures.SalesAllocationTest.setUp(self)
        self.cast.course_back_rate = 50
        self.cast.option_back_rate = 100
        self.cast.save()
        self.store.nomination_fullback_enabled = True
        self.store.save()
        self.fixed.amount = 1000
        self.fixed.save()
        self.order.course_price = 18000
        self.order.options_price = 5000
        self.order.extension_duration = 30
        self.order.extension_price = 6000
        self.order.nomination_fee_price = 1000
        self.order.discount_type_snapshot = "fixed"
        self.order.discount_value_snapshot = 2000
        self.order.save()
        recalculate_order_total(self.order)

    def submit(self, version=2):
        response = self.cast_client.post("/api/cast/checkout/", {"room_cash_taken_amount": 3000}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        checkout = CastDailyCheckout.objects.get(pk=response.data["id"])
        if version == 1:
            checkout.estimated_pay = 15000
            checkout.pay_calculation_version = 1
            checkout.save(update_fields=["estimated_pay", "pay_calculation_version"])
        return checkout

    def correct_extension(self, amount):
        self.order.refresh_from_db()
        return self.manager_client.post(f"/api/orders/{self.order.pk}/correct-accounting/", {
            "reason": "延長料金を訂正", "expected_updated_at": self.order.updated_at.isoformat(),
            "extension_duration": 30, "extension_price": amount,
        }, format="json")

    def test_all_live_paths_include_extension_and_preserve_other_components(self, now):
        own = _compute_cast_done_sales(self.cast, self.day)
        dashboard = get_sales_dashboard(self.store, self.day, self.day)
        detail = get_sales_cast_detail(self.store, self.day, self.day, self.cast)
        checkout = self.cast_client.get("/api/cast/checkout/").data
        daily = self.manager_client.get(f"/api/op/daily-settlement/?date={self.day}").data["rows"][0]
        self.assertEqual(self.order.total_price, 28000)
        self.assertEqual([own["estimated_pay"], dashboard["by_cast"][0]["estimated_pay"],
                          detail["totals"]["estimated_pay"], checkout["estimated_pay"], daily["back_amount"]], [18000] * 5)
        self.assertEqual(detail["orders"][0]["estimated_pay"], 18000)
        self.assertEqual(detail["breakdowns"]["extensions"][0]["amount"], 6000)
        self.assertEqual((daily["compensation"], checkout["compensation"]), (17000, 17000))
        self.assertEqual(daily["total_sales"] - daily["compensation"], 11000)
        exported = self.manager_client.get(f"/api/op/daily-settlement/export/?date={self.day}")
        self.assertContains(exported, "17000")
        self.assertEqual(SmsLog.objects.count(), 0)
        self.assertEqual(LineNotificationLog.objects.count(), 0)

    def test_extension_uses_course_rate_and_same_rounding_bucket(self, now):
        for rate, expected in [(0, 6000), (50, 18000), (100, 30000)]:
            with self.subTest(rate=rate):
                self.cast.course_back_rate = rate
                self.assertEqual(compensation_total(self.cast, 18000, 5000, 1000, 6000), expected)
        self.cast.course_back_rate = 50
        self.assertEqual(compensation_total(self.cast, 10001, 0, extension_sales=1), 5001)
        self.assertEqual(compensation_total(self.cast, 10001, 0, extension_sales=1, version=1), 5000)
        with self.assertRaises(ValueError):
            compensation_total(self.cast, 10000, 0, version=99)

    def test_multi_order_detail_allocates_extension_without_losing_yen(self, now):
        second = Order.objects.get(pk=self.order.pk)
        second.pk = None
        second.start += timedelta(hours=2)
        second.end += timedelta(hours=2)
        second.course_price = 10001
        second.extension_price = 1
        second.save()
        detail = get_sales_cast_detail(self.store, self.day, self.day, self.cast)
        dashboard = get_sales_dashboard(self.store, self.day, self.day)
        self.assertEqual(sum(row["estimated_pay"] for row in detail["orders"]), detail["totals"]["estimated_pay"])
        self.assertEqual(detail["totals"]["estimated_pay"], dashboard["by_cast"][0]["estimated_pay"])

    def test_new_submission_records_version_and_corrects_extension_delta(self, now):
        checkout = self.submit()
        self.assertEqual((checkout.pay_calculation_version, checkout.estimated_pay), (2, 18000))
        response = self.correct_extension(8000)
        self.assertEqual(response.status_code, 200, response.data)
        checkout.refresh_from_db()
        self.assertEqual((checkout.estimated_pay, checkout.room_cash_taken_amount), (19000, 3000))
        self.assertEqual(list(checkout.expense_snapshots.values_list("amount", flat=True)), [1000])

    @patch("core.views.notify_order_cancelled")
    def test_legacy_and_new_submissions_can_cancel_without_rewriting_cash(self, now, notify):
        # Each mode is checked on its own saved basis; the actual cash never changes.
        for version in (1, 2):
            with self.subTest(version=version):
                with self.captureOnCommitCallbacks(execute=False):
                    checkout = self.submit(version)
                    self.order.refresh_from_db()
                    response = self.manager_client.post(f"/api/orders/{self.order.pk}/cancel/", {
                        "expected_updated_at": self.order.updated_at.isoformat(),
                    }, format="json")
                    self.assertEqual(response.status_code, 200, response.data)
                    checkout.refresh_from_db()
                    self.assertEqual(checkout.estimated_pay, 0)
                    self.assertEqual(checkout.room_cash_taken_amount, 3000)
                    self.assertEqual(checkout.pay_calculation_version, version)
                    checkout.delete()
                    self.order.status = "DONE"
                    self.order.save()

    def test_legacy_reads_and_extension_correction_preserve_saved_basis(self, now):
        checkout = self.submit(version=1)
        before = (checkout.estimated_pay, checkout.room_cash_taken_amount, checkout.daily_expense_total)
        live = get_sales_dashboard(self.store, self.day, self.day)["by_cast"][0]["estimated_pay"]
        self.assertEqual(live, 18000)
        self.assertEqual(self.cast_client.get("/api/cast/checkout/").data["estimated_pay"], 15000)
        daily = self.manager_client.get(f"/api/op/daily-settlement/?date={self.day}").data["rows"][0]
        self.assertEqual(daily["back_amount"], 15000)
        checkout.refresh_from_db()
        self.assertEqual((checkout.estimated_pay, checkout.room_cash_taken_amount, checkout.daily_expense_total), before)
        response = self.correct_extension(8000)
        self.assertEqual(response.status_code, 200, response.data)
        checkout.refresh_from_db()
        self.assertEqual((checkout.estimated_pay, checkout.pay_calculation_version), (15000, 1))
        self.assertEqual(checkout.room_cash_taken_amount, 3000)

    def test_returned_legacy_submission_explicitly_resubmits_under_new_formula(self, now):
        checkout = self.submit(version=1)
        checkout.status = "RETURNED"
        checkout.save(update_fields=["status"])
        preview = self.cast_client.get("/api/cast/checkout/")
        self.assertEqual(preview.data["estimated_pay"], 18000)
        response = self.cast_client.post("/api/cast/checkout/", {"room_cash_taken_amount": 3000}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        checkout.refresh_from_db()
        self.assertEqual((checkout.estimated_pay, checkout.pay_calculation_version), (18000, 2))

    def test_locked_snapshot_and_actual_cash_are_not_recalculated(self, now):
        snapshot = {"date": str(self.day), "rows": [{"back_amount": 15000}], "totals": {"back_amount": 15000}}
        DailySettlement.objects.create(store=self.store, date=self.day, status="LOCKED", snapshot_json=snapshot)
        response = self.manager_client.get(f"/api/op/daily-settlement/?date={self.day}")
        self.assertEqual(response.data["rows"], snapshot["rows"])
        self.assertEqual(self.correct_extension(8000).status_code, 400)

    def test_old_process_inserts_keep_legacy_database_default(self, now):
        apps = MigrationLoader(connection).project_state([("core", "0105_legacy_customer_history")]).apps
        old_checkout = apps.get_model("core", "CastDailyCheckout").objects.create(
            store_id=self.store.pk, cast_id=self.cast.pk, date=self.day, estimated_pay=15000,
            room_cash_taken_amount=3000,
        )
        checkout = CastDailyCheckout.objects.get(pk=old_checkout.pk)
        self.assertEqual((checkout.pay_calculation_version, checkout.estimated_pay, checkout.room_cash_taken_amount), (1, 15000, 3000))


class CheckoutPayVersionMigrationTest(TransactionTestCase):
    def test_migration_marks_existing_as_legacy_without_changing_money(self):
        old_target = [("core", "0105_legacy_customer_history")]
        new_target = [("core", "0106_checkout_pay_calculation_version")]
        try:
            state = migrate_test_schema(old_target)
            Store = state.apps.get_model("core", "Store")
            Cast = state.apps.get_model("core", "Cast")
            Checkout = state.apps.get_model("core", "CastDailyCheckout")
            store = Store.objects.create(name="移行確認店舗")
            cast = Cast.objects.create(store_id=store.pk, name="移行確認キャスト")
            row = Checkout.objects.create(store_id=store.pk, cast_id=cast.pk, date="2026-10-02",
                estimated_pay=15000, room_cash_taken_amount=3000, office_cash_paid_amount=1000)
            migrate_test_schema(new_target)
            saved = CastDailyCheckout.objects.get(pk=row.pk)
            self.assertEqual(saved.pay_calculation_version, 1)
            self.assertEqual((saved.estimated_pay, saved.room_cash_taken_amount, saved.office_cash_paid_amount), (15000, 3000, 1000))
        finally:
            migrate_test_schema(new_target)
