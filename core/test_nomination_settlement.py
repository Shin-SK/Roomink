import csv
import io
from datetime import timedelta

from django.test import TestCase

from core.models import Order
from core.test_sales_allocation import SalesAllocationTest


class NominationSettlementTest(TestCase):
    setUp = SalesAllocationTest.setUp

    def prepare_four_orders(self, enabled=True):
        self.store.nomination_fullback_enabled = enabled
        self.store.save(update_fields=["nomination_fullback_enabled"])
        self.cast.course_back_rate = 50
        self.cast.option_back_rate = 100
        self.cast.save(update_fields=["course_back_rate", "option_back_rate"])
        self.fixed.amount = 2000
        self.fixed.save(update_fields=["amount"])
        original_start = self.order.start
        self.order.delete()
        for i, (price, discount, method) in enumerate([
            (23000, 1000, "CASH"), (18000, 2000, "CASH"),
            (20000, 1000, "CARD"), (20000, 1000, "CASH"),
        ]):
            self.order.pk = None
            self.order.course_price = price
            self.order.options_price = 5000
            self.order.nomination_fee_name = "本指名" if i == 0 else "写真指名"
            self.order.nomination_fee_price = 1000
            self.order.discount_amount = discount
            self.order.total_price = price + 5000 + 1000 - discount
            self.order.payment_method = method
            self.order.card_include_options = False
            self.order.start = original_start + timedelta(hours=i)
            self.order.end = self.order.start + timedelta(minutes=60)
            self.order.save()

    def test_live_csv_api_and_details_include_nomination_and_mixed_cash(self):
        self.prepare_four_orders()
        url = f"/api/op/daily-settlement/?date={self.day}"
        response = self.manager_client.get(url)
        self.assertEqual(response.status_code, 200)
        row = response.data["rows"][0]
        self.assertEqual(row["back_amount"], 64500)
        self.assertEqual(row["compensation"], 62500)
        self.assertEqual(row["total_sales"], 100000)
        self.assertEqual(row["customer_payment_surcharge"], 2000)
        self.assertEqual(row["store_allocation"], 39500)
        self.assertEqual(row["store_allocation"] - row["customer_payment_surcharge"], 37500)
        self.assertEqual(row["cash_sales_total"], 80000)
        self.assertEqual(row["cash_settlement_amount"], 17500)
        self.assertEqual(row["net_pay"], -17500)
        for _ in range(2):
            exported = self.manager_client.get(f"/api/op/daily-settlement/export/?date={self.day}")
            csv_row = list(csv.DictReader(io.StringIO(exported.content.decode("utf-8-sig"))))[0]
            self.assertEqual(csv_row["報酬"], "62500")
            self.assertEqual(csv_row["現金精算額（正＝店へ残す／負＝店から支払う）"], "17500")
        detail = self.manager_client.get(
            f"/api/op/sales-dashboard/cast-detail/?date_from={self.day}&date_to={self.day}&cast={self.cast.pk}"
        )
        self.assertEqual(detail.data["totals"]["estimated_pay"], 64500)
        self.assertEqual(sum(r["estimated_pay"] for r in detail.data["orders"]), 64500)

    def test_unconfirmed_store_policy_and_locked_export_are_preserved(self):
        self.prepare_four_orders(enabled=False)
        response = self.manager_client.get(f"/api/op/daily-settlement/?date={self.day}")
        self.assertEqual(response.data["rows"][0]["back_amount"], 60500)
        locked = self.manager_client.post("/api/op/daily-settlement/lock/", {"date": str(self.day)}, format="json")
        self.assertEqual(locked.status_code, 200)
        before = self.manager_client.get(f"/api/op/daily-settlement/export/?date={self.day}").content
        self.store.nomination_fullback_enabled = True
        self.store.save(update_fields=["nomination_fullback_enabled"])
        after = self.manager_client.get(f"/api/op/daily-settlement/export/?date={self.day}").content
        self.assertEqual(before, after)

    def test_csv_permission_boundaries(self):
        self.assertEqual(self.cast_client.get(f"/api/op/daily-settlement/export/?date={self.day}").status_code, 403)
