from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Cast, Course, Customer, Option, Order, Room, Store, UserProfile


User = get_user_model()
TOKYO = ZoneInfo("Asia/Tokyo")


class SalesCastDetailApiTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(
            name="明細テスト店舗",
            timezone="Asia/Tokyo",
            card_fee_rate=10,
        )
        manager = User.objects.create_user("detail_manager")
        UserProfile.objects.create(
            user=manager,
            store=self.store,
            role=UserProfile.Role.MANAGER,
        )
        staff = User.objects.create_user("detail_staff")
        UserProfile.objects.create(
            user=staff,
            store=self.store,
            role=UserProfile.Role.STAFF,
        )
        self.manager_client = APIClient()
        self.manager_client.force_authenticate(manager)
        self.staff_client = APIClient()
        self.staff_client.force_authenticate(staff)

        self.cast = Cast.objects.create(
            store=self.store,
            name="明細 花",
            course_back_rate=50,
            option_back_rate=100,
        )
        self.room = Room.objects.create(store=self.store, name="Aルーム")
        self.customer = Customer.objects.create(
            store=self.store,
            phone="09000000001",
            display_name="テスト顧客",
        )
        self.course = Course.objects.create(
            store=self.store,
            name="100分コース",
            duration=100,
            price=10000,
        )
        self.option = Option.objects.create(
            store=self.store,
            name="衣装チェンジ",
            price=2000,
        )
        self.order = Order.objects.create(
            store=self.store,
            cast=self.cast,
            room=self.room,
            customer=self.customer,
            course=self.course,
            course_name=self.course.name,
            course_price=10000,
            options_price=2000,
            nomination_fee_name="写真指名",
            nomination_fee_price=1000,
            discount_name="テスト割引",
            discount_amount=1000,
            medium_name="公式HP",
            total_price=12000,
            payment_method=Order.PaymentMethod.CARD,
            card_include_options=True,
            start=datetime(2026, 10, 7, 13, 0, tzinfo=TOKYO),
            end=datetime(2026, 10, 7, 14, 40, tzinfo=TOKYO),
            status=Order.Status.DONE,
        )
        self.order.options.add(self.option)
        self.url = (
            "/api/op/sales-dashboard/cast-detail/"
            f"?date_from=2026-10-07&date_to=2026-10-07&cast={self.cast.id}"
        )

    def test_manager_can_read_order_and_breakdown_detail(self):
        response = self.manager_client.get(self.url)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["cast_name"], "明細 花")
        self.assertEqual(response.data["totals"], {
            "orders": 1,
            "sales": 12000,
            "customer_payment_surcharge": 1200,
            "customer_payment_total": 13200,
            "estimated_pay": 7000,
            "store_allocation_estimate": 6200,
        })
        self.assertEqual(response.data["orders"][0]["customer_name"], "テスト顧客")
        self.assertEqual(response.data["orders"][0]["option_names"], ["衣装チェンジ"])
        self.assertEqual(response.data["orders"][0]["estimated_pay"], 7000)
        self.assertEqual(response.data["orders"][0]["store_allocation_estimate"], 6200)
        self.assertEqual(response.data["breakdowns"]["courses"][0]["amount"], 10000)
        self.assertEqual(response.data["breakdowns"]["options"][0]["amount"], 2000)
        self.assertEqual(response.data["breakdowns"]["nominations"][0]["amount"], 1000)
        self.assertEqual(response.data["breakdowns"]["discounts"][0]["amount"], 1000)
        self.assertEqual(response.data["breakdowns"]["media"][0]["name"], "公式HP")

    def test_staff_cannot_read_cast_detail(self):
        response = self.staff_client.get(self.url)
        self.assertEqual(response.status_code, 403, response.data)

    def test_cast_from_another_store_is_not_visible(self):
        other_store = Store.objects.create(name="別店舗")
        other_cast = Cast.objects.create(store=other_store, name="別店舗キャスト")

        response = self.manager_client.get(
            "/api/op/sales-dashboard/cast-detail/"
            f"?date_from=2026-10-07&date_to=2026-10-07&cast={other_cast.id}"
        )

        self.assertEqual(response.status_code, 404, response.data)

    def test_room_and_payment_filters_match_dashboard(self):
        response = self.manager_client.get(f"{self.url}&payment_method=CASH")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["totals"]["orders"], 0)
        self.assertEqual(response.data["orders"], [])

    def test_cast_is_required(self):
        response = self.manager_client.get(
            "/api/op/sales-dashboard/cast-detail/"
            "?date_from=2026-10-07&date_to=2026-10-07"
        )
        self.assertEqual(response.status_code, 400, response.data)

