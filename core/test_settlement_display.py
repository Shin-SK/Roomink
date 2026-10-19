import csv
import io

from core.models import DailySettlement
from core.services.sales import settlement_store_share
from core import test_sales_allocation
from django.test import TestCase


class SettlementDisplayTest(TestCase):
    setUp = test_sales_allocation.SalesAllocationTest.setUp

    def test_csv_uses_operational_share_and_management_report_retains_surcharge(self):
        self.order.payment_method = "CARD"
        self.order.card_include_options = True
        self.order.save()
        url = f"/api/op/daily-settlement/export/?date={self.day}"
        response = self.manager_client.get(url)
        rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
        self.assertEqual(rows[0]["店落ち"], "15000")
        self.assertEqual(rows[0]["報酬"], "9000")
        self.assertEqual(rows[1]["店落ち"], "15000")
        for field in ("カード決済加算", "お客様決済額", "店舗側決済手数料見込み"):
            self.assertNotIn(field, rows[0])
        dashboard = self.manager_client.get(f"/api/op/sales-dashboard/?date_from={self.day}&date_to={self.day}")
        self.assertEqual(dashboard.data["customer_payment_surcharge"], 2400)
        self.assertEqual(dashboard.data["customer_payment_total"], 26400)

    def test_locked_snapshot_is_unchanged_when_exported_with_new_display(self):
        snapshot = {"rows": [{"cast_name": "検証", "total_sales": 52000, "compensation": 31000,
                              "customer_payment_surcharge": 2600, "store_allocation": 23600}],
                    "totals": {"total_sales": 52000, "compensation": 31000,
                               "customer_payment_surcharge": 2600, "store_allocation": 23600}}
        settlement = DailySettlement.objects.create(store=self.store, date=self.day, status="LOCKED", snapshot_json=snapshot)
        response = self.manager_client.get(f"/api/op/daily-settlement/export/?date={self.day}")
        rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
        self.assertEqual(rows[0]["店落ち"], "21000")
        self.assertEqual(rows[1]["店落ち"], "21000")
        settlement.refresh_from_db()
        self.assertEqual(settlement.snapshot_json, snapshot)

    def test_unknown_legacy_share_is_blank_and_negative_share_is_preserved(self):
        self.assertEqual(settlement_store_share({}), "")
        self.assertEqual(settlement_store_share({"total_sales": 0, "compensation": 1000}), -1000)
