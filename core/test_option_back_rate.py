from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Cast, Course, Customer, Order, Room, ShiftAssignment, Store, UserProfile
from core.serializers import CastSerializer
from core.views import _compute_cast_done_sales


User = get_user_model()
TOKYO = ZoneInfo("Asia/Tokyo")


class OptionBackRateTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="オプションバック店舗", timezone="Asia/Tokyo")
        self.cast_user = User.objects.create_user("option_rate_cast", password="pass")
        UserProfile.objects.create(
            user=self.cast_user,
            store=self.store,
            role=UserProfile.Role.CAST,
        )
        self.cast = Cast.objects.create(
            store=self.store,
            user=self.cast_user,
            name="バック率テスト",
            course_back_rate=50,
            option_back_rate=40,
        )
        self.room = Room.objects.create(store=self.store, name="101")
        ShiftAssignment.objects.create(
            store=self.store,
            cast=self.cast,
            room=self.room,
            date=date(2026, 8, 19),
            start_time=time(17, 0),
            end_time=time(23, 0),
        )
        self.customer = Customer.objects.create(
            store=self.store,
            phone="09011112222",
            display_name="テスト顧客",
        )
        self.course = Course.objects.create(
            store=self.store,
            name="60分",
            duration=60,
            price=10000,
        )
        Order.objects.create(
            store=self.store,
            cast=self.cast,
            room=self.room,
            customer=self.customer,
            course=self.course,
            course_name=self.course.name,
            course_price=10000,
            options_price=5001,
            total_price=15001,
            start=datetime(2026, 8, 19, 18, 0, tzinfo=TOKYO),
            end=datetime(2026, 8, 19, 19, 0, tzinfo=TOKYO),
            status=Order.Status.DONE,
        )

        manager = User.objects.create_user("option_rate_manager", password="pass")
        UserProfile.objects.create(
            user=manager,
            store=self.store,
            role=UserProfile.Role.MANAGER,
        )
        self.manager_client = APIClient()
        self.manager_client.force_authenticate(manager)

    def test_partial_option_back_rate_is_used_consistently(self):
        result = _compute_cast_done_sales(self.cast, date(2026, 8, 19))
        self.assertEqual(result["estimated_pay"], 7000)

        settlement = self.manager_client.get("/api/op/daily-settlement/?date=2026-08-19")
        self.assertEqual(settlement.status_code, 200, settlement.data)
        row = settlement.data["rows"][0]
        self.assertEqual(row["option_back_rate"], 40)
        self.assertEqual(row["back_amount"], 7000)

        dashboard = self.manager_client.get(
            "/api/op/sales-dashboard/?date_from=2026-08-19&date_to=2026-08-19"
        )
        self.assertEqual(dashboard.status_code, 200, dashboard.data)
        cast_row = dashboard.data["by_cast"][0]
        self.assertEqual(cast_row["option_back_rate"], 40)
        self.assertEqual(cast_row["estimated_pay"], 7000)

    def test_zero_and_full_option_back_rates(self):
        self.cast.option_back_rate = 0
        self.cast.save(update_fields=["option_back_rate"])
        self.assertEqual(
            _compute_cast_done_sales(self.cast, date(2026, 8, 19))["estimated_pay"],
            5000,
        )

        self.cast.option_back_rate = 100
        self.cast.save(update_fields=["option_back_rate"])
        self.assertEqual(
            _compute_cast_done_sales(self.cast, date(2026, 8, 19))["estimated_pay"],
            10001,
        )

    def test_legacy_fullback_payload_is_kept_compatible(self):
        serializer = CastSerializer(
            self.cast,
            data={"option_fullback_enabled": True},
            partial=True,
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        updated = serializer.save()
        self.assertEqual(updated.option_back_rate, 100)
        self.assertTrue(updated.option_fullback_enabled)

    def test_option_back_rate_is_limited_to_zero_through_one_hundred(self):
        serializer = CastSerializer(
            self.cast,
            data={"option_back_rate": 101},
            partial=True,
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("option_back_rate", serializer.errors)
