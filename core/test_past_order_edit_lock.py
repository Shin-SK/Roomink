from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Cast, Course, Customer, Order, Room, Store, UserProfile
from core.services.business_datetime import (
    build_store_datetime,
    business_date_for_datetime,
)


User = get_user_model()


class PastOrderEditLockTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="過去予約ロック店舗", timezone="Asia/Tokyo")
        self.manager = self.create_operator("lock_manager", UserProfile.Role.MANAGER)
        self.staff = self.create_operator("lock_staff", UserProfile.Role.STAFF)
        cast_user = self.create_operator("lock_cast", UserProfile.Role.CAST)
        self.cast = Cast.objects.create(store=self.store, user=cast_user, name="ロックキャスト")
        self.room = Room.objects.create(store=self.store, name="101")
        self.customer = Customer.objects.create(
            store=self.store,
            phone="09077778888",
            display_name="ロック顧客",
        )
        self.course = Course.objects.create(
            store=self.store,
            name="60分",
            duration=60,
            price=10000,
        )
        self.current_business_date = business_date_for_datetime(
            timezone.now(),
            self.store.timezone,
        )
        self.past_order = self.create_order(
            self.current_business_date - timedelta(days=1),
            memo="変更前",
        )
        self.current_order = self.create_order(
            self.current_business_date,
            memo="当日変更前",
        )

        self.manager_client = self.client_as(self.manager)
        self.staff_client = self.client_as(self.staff)
        self.cast_client = self.client_as(cast_user)

    def create_operator(self, username, role):
        user = User.objects.create_user(username)
        UserProfile.objects.create(user=user, store=self.store, role=role)
        return user

    def create_order(self, business_date, memo):
        start = build_store_datetime(
            business_date,
            time(18, 0),
            timezone_name=self.store.timezone,
        )
        return Order.objects.create(
            store=self.store,
            cast=self.cast,
            room=self.room,
            customer=self.customer,
            course=self.course,
            course_name=self.course.name,
            course_price=self.course.price,
            total_price=self.course.price,
            start=start,
            end=start + timedelta(hours=1),
            status=Order.Status.REQUESTED,
            memo=memo,
        )

    def client_as(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_staff_and_cast_cannot_patch_past_business_day_order(self):
        endpoint = f"/api/orders/{self.past_order.id}/"

        for label, client in (("staff", self.staff_client), ("cast", self.cast_client)):
            with self.subTest(user=label):
                response = client.patch(endpoint, {"memo": "不正変更"}, format="json")
                self.assertEqual(response.status_code, 403, response.data)

        self.past_order.refresh_from_db()
        self.assertEqual(self.past_order.memo, "変更前")

    def test_staff_cannot_use_any_past_order_mutation_route(self):
        mutations = [
            ("post", "confirm/", {}),
            ("post", "cancel/", {}),
            ("post", "done/", {}),
            ("post", "apply_extension/", {"extension_id": None}),
            ("post", "apply_nomination_fee/", {"nomination_fee_id": None}),
            ("post", "apply_discount/", {"discount_id": None}),
            ("post", "apply_medium/", {"medium_id": None}),
            ("delete", "", None),
        ]

        for method, suffix, payload in mutations:
            order = self.create_order(
                self.current_business_date - timedelta(days=1),
                memo="経路別変更前",
            )
            endpoint = f"/api/orders/{order.id}/{suffix}"
            with self.subTest(method=method, endpoint=endpoint):
                response = getattr(self.staff_client, method)(
                    endpoint,
                    payload,
                    format="json",
                )
                self.assertEqual(response.status_code, 403, response.data)
                order.refresh_from_db()
                self.assertEqual(order.status, Order.Status.REQUESTED)
                self.assertEqual(order.memo, "経路別変更前")

    def test_manager_can_update_past_business_day_order(self):
        before = self.manager_client.get(f"/api/orders/{self.past_order.id}/")
        self.assertTrue(before.data["is_past_business_day"])
        self.assertTrue(before.data["can_modify"])

        response = self.manager_client.patch(
            f"/api/orders/{self.past_order.id}/",
            {"memo": "管理者変更"},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.past_order.refresh_from_db()
        self.assertEqual(self.past_order.memo, "管理者変更")

    def test_staff_can_still_update_current_business_day_order(self):
        before = self.staff_client.get(f"/api/orders/{self.current_order.id}/")
        self.assertFalse(before.data["is_past_business_day"])
        self.assertTrue(before.data["can_modify"])

        response = self.staff_client.patch(
            f"/api/orders/{self.current_order.id}/",
            {"memo": "当日スタッフ変更"},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.current_order.refresh_from_db()
        self.assertEqual(self.current_order.memo, "当日スタッフ変更")

    def test_staff_cannot_move_current_order_into_past_business_day(self):
        original_start = self.current_order.start
        past_start = build_store_datetime(
            self.current_business_date - timedelta(days=1),
            time(20, 0),
            timezone_name=self.store.timezone,
        )

        response = self.staff_client.patch(
            f"/api/orders/{self.current_order.id}/",
            {
                "start": past_start.isoformat(),
                "end": (past_start + timedelta(hours=1)).isoformat(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, 403, response.data)
        self.current_order.refresh_from_db()
        self.assertEqual(self.current_order.start, original_start)

    def test_staff_cannot_create_backdated_order(self):
        past_start = build_store_datetime(
            self.current_business_date - timedelta(days=1),
            time(21, 0),
            timezone_name=self.store.timezone,
        )
        original_count = Order.objects.count()

        response = self.staff_client.post(
            "/api/orders/",
            {
                "cast": self.cast.id,
                "customer": self.customer.id,
                "course": self.course.id,
                "start": past_start.isoformat(),
                "end": (past_start + timedelta(hours=1)).isoformat(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, 403, response.data)
        self.assertEqual(Order.objects.count(), original_count)

    def test_past_order_remains_readable(self):
        response = self.staff_client.get(f"/api/orders/{self.past_order.id}/")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["id"], self.past_order.id)
        self.assertTrue(response.data["is_past_business_day"])
        self.assertFalse(response.data["can_modify"])
