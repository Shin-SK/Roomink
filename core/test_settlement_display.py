import csv
import io

from core.models import Cast, CastDailyCheckout, CastExpense, DailySettlement, ShiftAssignment
from core.services.sales import settlement_store_share
from core import test_sales_allocation
from django.test import TestCase


class SettlementDisplayTest(TestCase):
    setUp = test_sales_allocation.SalesAllocationTest.setUp

    def test_absent_without_accounting_is_hidden_in_api_csv_and_new_lock(self):
        shift = ShiftAssignment.objects.get(cast=self.cast)
        absent = Cast.objects.create(store=self.store, name='当欠・売上なし')
        ShiftAssignment.objects.create(store=self.store, cast=absent, date=self.day,
            start_time=shift.start_time, end_time=shift.end_time, is_absent=True)
        url = f'/api/op/daily-settlement/?date={self.day}'
        before = self.manager_client.get(url)
        self.assertEqual([r['cast_id'] for r in before.data['rows']], [self.cast.pk])
        exported = self.manager_client.get(f'/api/op/daily-settlement/export/?date={self.day}')
        self.assertNotIn(absent.name, exported.content.decode('utf-8-sig'))
        locked = self.manager_client.post('/api/op/daily-settlement/lock/', {'date': str(self.day)}, format='json')
        self.assertEqual(locked.status_code, 200, locked.data)
        self.assertEqual(self.manager_client.get(url).data['rows'], before.data['rows'])

    def test_absent_with_done_sales_keeps_money(self):
        ShiftAssignment.objects.filter(cast=self.cast).update(is_absent=True)
        row = self.manager_client.get(f'/api/op/daily-settlement/?date={self.day}').data['rows'][0]
        self.assertEqual(row['total_sales'], 24000)
        self.assertEqual(row['compensation'], 9000)

    def test_absent_with_checkout_or_daily_expense_remains_visible(self):
        self.order.delete()
        ShiftAssignment.objects.filter(cast=self.cast).update(is_absent=True)
        checkout = CastDailyCheckout.objects.create(store=self.store, cast=self.cast, date=self.day)
        url = f'/api/op/daily-settlement/?date={self.day}'
        self.assertEqual(len(self.manager_client.get(url).data['rows']), 1)
        checkout.delete()
        CastExpense.objects.create(store=self.store, cast=self.cast, date=self.day, name='記録済み雑費', amount=1000)
        self.assertEqual(len(self.manager_client.get(url).data['rows']), 1)

    def test_a_non_absent_shift_preserves_zero_sales_row(self):
        self.order.delete()
        response = self.manager_client.get(f'/api/op/daily-settlement/?date={self.day}')
        self.assertEqual(len(response.data['rows']), 1)
        self.assertEqual(response.data['rows'][0]['total_sales'], 0)

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
