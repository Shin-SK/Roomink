from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase

from core.models import CastDailyCheckout, CastExpense, CastCheckoutExpenseSnapshot
from core import test_sales_allocation
from core.services.sales import get_sales_dashboard, get_sales_dashboard_csv


class CashSplitCheckoutTest(TestCase):
    setUp = test_sales_allocation.SalesAllocationTest.setUp

    def test_mixed_card_cash_totals_details_and_csv_agree(self):
        self.order.payment_method = "CARD"
        self.order.course_price = 25000
        self.order.options_price = 5000
        self.order.nomination_fee_price = 1000
        self.order.total_price = 31000
        self.order.card_include_options = False
        self.order.save()
        data = get_sales_dashboard(self.store, self.day, self.day)
        rows = {r["payment_method"]: r for r in data["by_payment_method"]}
        self.assertEqual(rows["CARD"]["sales"], 26000)
        self.assertEqual(rows["CARD"]["customer_payment_total"], 28600)
        self.assertEqual(rows["CASH"]["sales"], 5000)
        self.assertEqual(sum(r["sales"] for r in rows.values()), data["total_sales"])
        self.assertEqual(sum(r["customer_payment_total"] for r in rows.values()), data["customer_payment_total"])
        detail = self.manager_client.get(f"/api/op/sales-dashboard/cast-detail/?date_from={self.day}&date_to={self.day}&cast={self.cast.pk}")
        self.assertEqual(detail.data["orders"][0]["card_payment_total"], 28600)
        self.assertEqual(detail.data["orders"][0]["cash_payment_total"], 5000)
        exported = get_sales_dashboard_csv(self.store, self.day, self.day)
        self.assertIn("カード,26000,1,2600,28600", exported)
        self.assertIn("現金,5000,1,0,5000", exported)

    def test_options_included_in_card_are_not_counted_twice(self):
        self.order.payment_method = "CARD"
        self.order.card_include_options = True
        self.order.save()
        data = get_sales_dashboard(self.store, self.day, self.day)
        self.assertEqual(len(data["by_payment_method"]), 1)
        self.assertEqual(data["by_payment_method"][0]["customer_payment_total"], 26400)

    @patch("core.views.timezone.now", return_value=datetime(2026, 10, 2, 20, tzinfo=ZoneInfo("Asia/Tokyo")))
    def test_zero_done_waives_fixed_costs_and_preserves_individual_cost_after_submission(self, _now):
        self.order.status = "CANCELLED"
        self.order.save()
        cost = CastExpense.objects.create(store=self.store, cast=self.cast, date=self.day, name="個別備品", amount=300)
        before = self.cast_client.get("/api/cast/checkout/").data
        self.assertEqual(before["fixed_expense_total"], 0)
        self.assertEqual(before["daily_expense_total"], 300)
        self.assertEqual(before["compensation"], -300)
        submitted = self.cast_client.post("/api/cast/checkout/", {"room_cash_taken_amount": 0}, format="json")
        self.assertEqual(submitted.status_code, 201, submitted.data)
        self.assertEqual(submitted.data["compensation_amount"], -300)
        self.assertTrue(all(r["amount"] == 0 for r in submitted.data["expense_snapshots"]))
        cost.amount = 900
        cost.save()
        after = self.cast_client.get("/api/cast/checkout/").data
        self.assertEqual(after["compensation"], -300)
        settlement = self.manager_client.get(f"/api/op/daily-settlement/?date={self.day}")
        self.assertEqual(settlement.data["rows"][0]["fixed_expense_total"], 0)
        self.assertEqual(settlement.data["rows"][0]["daily_expense_total"], 300)

    @patch("core.views.timezone.now", return_value=datetime(2026, 10, 2, 20, tzinfo=ZoneInfo("Asia/Tokyo")))
    def test_zero_done_without_individual_cost_and_legacy_snapshot_unchanged(self, _now):
        self.order.status = "CANCELLED"
        self.order.save()
        self.assertEqual(self.cast_client.get("/api/cast/checkout/").data["compensation"], 0)
        old = CastDailyCheckout.objects.create(store=self.store, cast=self.cast, date=self.day, done_count=0)
        CastCheckoutExpenseSnapshot.objects.create(checkout=old, template=self.fixed, name="旧雑費", amount=5000)
        data = self.cast_client.get("/api/cast/checkout/").data
        self.assertEqual(data["fixed_expense_total"], 5000)
        self.assertEqual(data["checkout"]["compensation_amount"], -5000)
        old.refresh_from_db()
        self.assertIsNone(old.daily_expense_total)

    @patch("core.views.timezone.now", return_value=datetime(2026, 10, 2, 20, tzinfo=ZoneInfo("Asia/Tokyo")))
    def test_cast_cash_received_excludes_card_charge_and_other_casts(self, _now):
        self.order.payment_method = "CARD"
        self.order.card_include_options = False
        self.order.save()
        data = self.cast_client.get("/api/cast/checkout/").data
        self.assertEqual(data["cash_sales_total"], 4000)
        self.order.card_include_options = True
        self.order.save()
        self.assertEqual(self.cast_client.get("/api/cast/checkout/").data["cash_sales_total"], 0)
