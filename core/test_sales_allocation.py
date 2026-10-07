import csv
import io
from datetime import date, datetime, time
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import (
    Cast, CastAdjustment, CastExpense, CastExpenseTemplate, Course, Customer, Order, Room,
    ShiftAssignment, Store, UserProfile,
)


class SalesAllocationTest(TestCase):
    def setUp(self):
        self.day = date(2026, 10, 2)
        self.store = Store.objects.create(name="配分検証店", timezone="Asia/Tokyo", line_is_enabled=False)
        cast_user = get_user_model().objects.create_user("allocation-cast")
        UserProfile.objects.create(user=cast_user, store=self.store, role=UserProfile.Role.CAST)
        self.cast = Cast.objects.create(
            store=self.store, user=cast_user, name="配分キャスト", course_back_rate=70,
        )
        manager = get_user_model().objects.create_user("allocation-manager")
        UserProfile.objects.create(user=manager, store=self.store, role=UserProfile.Role.MANAGER)
        self.cast_client = APIClient()
        self.cast_client.force_authenticate(cast_user)
        self.manager_client = APIClient()
        self.manager_client.force_authenticate(manager)
        room = Room.objects.create(store=self.store, name="101")
        customer = Customer.objects.create(store=self.store, phone="09012345678", display_name="顧客")
        course = Course.objects.create(store=self.store, name="60分", duration=60, price=20000)
        ShiftAssignment.objects.create(
            store=self.store, date=self.day, cast=self.cast, room=room,
            start_time=time(17), end_time=time(23),
        )
        self.order = Order.objects.create(
            store=self.store, cast=self.cast, room=room, customer=customer, course=course,
            course_name=course.name, course_price=20000, options_price=4000, total_price=24000,
            payment_method=Order.PaymentMethod.CASH,
            start=datetime(2026, 10, 2, 18, tzinfo=ZoneInfo("Asia/Tokyo")),
            end=datetime(2026, 10, 2, 19, tzinfo=ZoneInfo("Asia/Tokyo")),
            status=Order.Status.DONE,
        )
        self.fixed = CastExpenseTemplate.objects.create(
            store=self.store, cast=self.cast, name="固定雑費", amount=5000,
        )

    @patch("core.views.timezone.now", return_value=datetime(2026, 10, 2, 20, tzinfo=ZoneInfo("Asia/Tokyo")))
    def test_checkout_and_daily_settlement_share_expense_and_allocation(self, _now):
        # 24,000円売上、バック14,000円、固定雑費5,000円。
        checkout = self.cast_client.get("/api/cast/checkout/")
        settlement = self.manager_client.get("/api/op/daily-settlement/?date=2026-10-02")
        self.assertEqual(checkout.status_code, 200, checkout.data)
        self.assertEqual(settlement.status_code, 200, settlement.data)
        for values in (checkout.data, settlement.data["rows"][0], settlement.data["totals"]):
            self.assertEqual(values["fixed_expense_total"], 5000)
            self.assertEqual(values["daily_expense_total"], 0)
            self.assertEqual(values["compensation"], 9000)
            self.assertEqual(values["store_allocation"], 15000)

        CastExpense.objects.create(
            store=self.store, cast=self.cast, date=self.day,
            name="当日雑費", amount=1000, per_order=True,
        )
        checkout = self.cast_client.get("/api/cast/checkout/")
        settlement = self.manager_client.get("/api/op/daily-settlement/?date=2026-10-02")
        for values in (checkout.data, settlement.data["rows"][0]):
            self.assertEqual(values["expense_total"], 6000)
            self.assertEqual(values["compensation"], 8000)
            self.assertEqual(values["store_allocation"], 16000)

        csv_response = self.manager_client.get("/api/op/daily-settlement/export/?date=2026-10-02")
        self.assertEqual(csv_response.status_code, 200)
        csv_rows = list(csv.DictReader(io.StringIO(csv_response.content.decode("utf-8-sig"))))
        self.assertEqual(csv_rows[0]["報酬"], "8000")
        self.assertEqual(csv_rows[0]["店舗配分"], "16000")

    def test_lock_recalculates_instead_of_trusting_client_values(self):
        response = self.manager_client.post(
            "/api/op/daily-settlement/lock/",
            {"date": self.day.isoformat(), "rows": [{"compensation": 999999}], "totals": {"store_allocation": 0}},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        locked = self.manager_client.get("/api/op/daily-settlement/?date=2026-10-02")
        self.assertEqual(locked.data["rows"][0]["compensation"], 9000)
        self.assertEqual(locked.data["totals"]["store_allocation"], 15000)

    @patch("core.views.timezone.now", return_value=datetime(2026, 10, 2, 20, tzinfo=ZoneInfo("Asia/Tokyo")))
    def test_card_fee_and_fixed_expense_snapshot(self, _now):
        self.order.payment_method = Order.PaymentMethod.CARD
        self.order.card_include_options = True
        self.order.save(update_fields=["payment_method", "card_include_options"])
        checkout = self.cast_client.get("/api/cast/checkout/")
        # 24,000円のカード決済は、お客様の請求額が10%上乗せの26,400円になる。
        # 上乗せ分は店舗配分に含め、店舗側手数料として二重に差し引かない。
        self.assertEqual(checkout.data["customer_payment_surcharge"], 2400)
        self.assertEqual(checkout.data["customer_payment_total"], 26400)
        self.assertEqual(checkout.data["payment_fee_estimate"], 0)
        self.assertEqual(checkout.data["compensation"], 9000)
        self.assertEqual(checkout.data["store_allocation"], 17400)

        dashboard = self.manager_client.get(
            "/api/op/sales-dashboard/?date_from=2026-10-02&date_to=2026-10-02",
        )
        self.assertEqual(dashboard.status_code, 200, dashboard.data)
        self.assertEqual(dashboard.data["customer_payment_surcharge"], 2400)
        self.assertEqual(dashboard.data["customer_payment_total"], 26400)
        self.assertEqual(dashboard.data["payment_fee_estimate"], 0)

        submit = self.cast_client.post(
            "/api/cast/checkout/",
            {"actual_take_home_amount": 0, "checklist_json": {}}, format="json",
        )
        self.assertEqual(submit.status_code, 201, submit.data)
        self.assertEqual(submit.data["customer_payment_surcharge"], 2400)
        self.assertEqual(submit.data["customer_payment_total"], 26400)
        unpaid = CastAdjustment.objects.get(source_checkout_id=submit.data["id"])
        self.assertEqual(unpaid.title, "現金不足による未払い")
        self.assertEqual(unpaid.amount, 9000)
        self.assertEqual(unpaid.status, CastAdjustment.Status.OPEN)
        self.fixed.amount = 7000
        self.fixed.save(update_fields=["amount"])
        checkout = self.cast_client.get("/api/cast/checkout/")
        settlement = self.manager_client.get("/api/op/daily-settlement/?date=2026-10-02")
        self.assertEqual(checkout.data["fixed_expense_total"], 5000)
        self.assertEqual(settlement.data["rows"][0]["fixed_expense_total"], 5000)
        self.assertEqual(settlement.data["rows"][0]["customer_payment_total"], 26400)
        self.assertEqual(settlement.data["rows"][0]["store_allocation"], 17400)

    @patch("core.views.timezone.now", return_value=datetime(2026, 10, 2, 20, tzinfo=ZoneInfo("Asia/Tokyo")))
    def test_line_disabled_hides_cast_entry_and_rejects_link(self, _now):
        today = self.cast_client.get("/api/cast/today/")
        self.assertEqual(today.status_code, 200, today.data)
        self.assertFalse(today.data["line_enabled"])
        self.assertFalse(today.data.get("line_link_code"))
        self.assertEqual(self.cast_client.get("/api/cast/line-link/").status_code, 403)
        self.assertEqual(self.cast_client.post("/api/cast/line-link/", {}, format="json").status_code, 403)
        self.assertEqual(self.manager_client.get("/api/op/line-settings/").status_code, 403)
