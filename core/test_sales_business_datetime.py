import csv
import io
from datetime import date, datetime, time
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import (
    Cast,
    Course,
    Customer,
    Order,
    Room,
    ShiftAssignment,
    Store,
    UserProfile,
)


User = get_user_model()
TOKYO = ZoneInfo("Asia/Tokyo")


class SalesBusinessDateTimeTest(TestCase):
    def setUp(self):
        self.business_date = date(2026, 7, 31)
        self.store = Store.objects.create(name="深夜売上店舗", timezone="Asia/Tokyo")
        cast_user = User.objects.create_user("late_sales_cast", password="pass")
        UserProfile.objects.create(
            user=cast_user,
            store=self.store,
            role=UserProfile.Role.CAST,
        )
        self.cast = Cast.objects.create(
            store=self.store,
            user=cast_user,
            name="深夜キャスト",
            course_back_rate=50,
        )
        self.room = Room.objects.create(
            store=self.store,
            name="101",
            area_name="深夜エリア",
        )
        self.customer = Customer.objects.create(
            store=self.store,
            phone="09055556666",
            display_name="深夜予約者",
        )
        self.course = Course.objects.create(
            store=self.store,
            name="60分",
            duration=60,
            price=10000,
        )
        ShiftAssignment.objects.create(
            store=self.store,
            date=self.business_date,
            cast=self.cast,
            room=self.room,
            start_time=time(18, 0),
            end_time=time(5, 0),
            end_day_offset=1,
        )
        self.order = Order.objects.create(
            store=self.store,
            cast=self.cast,
            room=self.room,
            customer=self.customer,
            course=self.course,
            course_name=self.course.name,
            course_price=self.course.price,
            total_price=self.course.price,
            payment_method=Order.PaymentMethod.CASH,
            start=datetime(2026, 8, 1, 3, 0, tzinfo=TOKYO),
            end=datetime(2026, 8, 1, 4, 0, tzinfo=TOKYO),
            status=Order.Status.DONE,
        )

        manager = User.objects.create_user("late_sales_manager", password="pass")
        UserProfile.objects.create(
            user=manager,
            store=self.store,
            role=UserProfile.Role.MANAGER,
        )
        self.manager_client = APIClient()
        self.manager_client.force_authenticate(manager)
        self.cast_client = APIClient()
        self.cast_client.force_authenticate(cast_user)

    def test_sales_summary_assigns_late_order_to_previous_business_date(self):
        response = self.manager_client.get(
            "/api/op/sales-summary/?date_from=2026-07-31&date_to=2026-07-31"
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["total_orders"], 1)
        self.assertEqual(response.data["total_sales"], 10000)
        self.assertEqual(response.data["by_day"], [
            {"date": "2026-07-31", "sales": 10000, "orders": 1},
        ])

        next_day = self.manager_client.get(
            "/api/op/sales-summary/?date_from=2026-08-01&date_to=2026-08-01"
        )
        self.assertEqual(next_day.status_code, 200, next_day.data)
        self.assertEqual(next_day.data["total_orders"], 0)

    @patch(
        "core.views.timezone.now",
        return_value=datetime(2026, 8, 1, 3, 30, tzinfo=TOKYO),
    )
    def test_today_range_uses_current_business_date(self, _now):
        manager_response = self.manager_client.get("/api/op/sales-summary/?range=today")
        cast_response = self.cast_client.get("/api/cast/today-sales/")

        self.assertEqual(manager_response.status_code, 200, manager_response.data)
        self.assertEqual(manager_response.data["date_from"], "2026-07-31")
        self.assertEqual(manager_response.data["total_orders"], 1)
        self.assertEqual(cast_response.status_code, 200, cast_response.data)
        self.assertEqual(cast_response.data["done_count"], 1)

    def test_sales_dashboard_uses_business_date_for_all_breakdowns(self):
        response = self.manager_client.get(
            "/api/op/sales-dashboard/?date_from=2026-07-31&date_to=2026-07-31"
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["total_orders"], 1)
        self.assertEqual(response.data["by_day"][0]["orders"], 1)
        self.assertEqual(response.data["by_cast"][0]["sales"], 10000)
        self.assertEqual(response.data["by_room"][0]["sales"], 10000)
        self.assertEqual(response.data["by_area"][0]["sales"], 10000)

    def test_sales_csv_outputs_business_date_and_extended_time(self):
        response = self.manager_client.get(
            "/api/op/sales-export.csv?date_from=2026-07-31&date_to=2026-07-31"
        )

        self.assertEqual(response.status_code, 200)
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][1], "2026-07-31")
        self.assertEqual(rows[1][2], "27:00")
        self.assertEqual(rows[1][3], "28:00")

    def test_daily_settlement_includes_late_order_in_shift_business_date(self):
        response = self.manager_client.get(
            "/api/op/daily-settlement/?date=2026-07-31"
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["rows"][0]["order_count"], 1)
        self.assertEqual(response.data["rows"][0]["course_sales"], 10000)
        self.assertEqual(response.data["rows"][0]["cash_sales_total"], 10000)
        self.assertEqual(response.data["rows"][0]["shift"], "18:00-29:00")

    @patch(
        "core.views.timezone.now",
        return_value=datetime(2026, 8, 1, 3, 30, tzinfo=TOKYO),
    )
    def test_cast_checkout_keeps_previous_business_date_after_midnight(self, _now):
        response = self.cast_client.get("/api/cast/checkout/")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["date"], "2026-07-31")
        self.assertEqual(response.data["done_count"], 1)
        self.assertEqual(response.data["total_sales"], 10000)
