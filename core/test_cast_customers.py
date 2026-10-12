from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Cast, Course, Customer, Order, Room, Store


User = get_user_model()


class CastCustomerManagementTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="キャスト顧客管理店")
        self.cast_user = User.objects.create_user("cast_customer_owner")
        self.cast = Cast.objects.create(
            store=self.store,
            user=self.cast_user,
            name="担当キャスト",
        )
        self.other_user = User.objects.create_user("cast_customer_other")
        self.other_cast = Cast.objects.create(
            store=self.store,
            user=self.other_user,
            name="別キャスト",
        )
        self.room = Room.objects.create(store=self.store, name="101")
        self.course = Course.objects.create(
            store=self.store,
            name="60分",
            duration=60,
            price=12000,
        )
        self.customer = Customer.objects.create(
            store=self.store,
            display_name="実利用者",
            phone="09011112222",
            staff_memo="運営のみ閲覧可",
        )
        self.contact = Customer.objects.create(
            store=self.store,
            display_name="予約連絡者",
            phone="09033334444",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.cast_user)
        self.other_client = APIClient()
        self.other_client.force_authenticate(self.other_user)

    def create_done_order(self, *, cast=None, recipient=None, customer=None, days_ago=1):
        start = timezone.now() - timedelta(days=days_ago)
        return Order.objects.create(
            store=self.store,
            cast=cast or self.cast,
            room=self.room,
            customer=customer or self.customer,
            service_recipient_customer=recipient,
            course=self.course,
            course_name=self.course.name,
            course_price=self.course.price,
            nomination_fee_name="本指名",
            total_price=self.course.price,
            start=start,
            end=start + timedelta(hours=1),
            status=Order.Status.DONE,
        )

    def test_lists_only_own_completed_effective_customers_without_private_fields(self):
        self.create_done_order(customer=self.contact, recipient=self.customer)
        self.create_done_order(cast=self.other_cast, customer=self.contact)

        response = self.client.get("/api/cast/customers/")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data["customers"]), 1)
        item = response.data["customers"][0]
        self.assertEqual(item["id"], self.customer.id)
        self.assertEqual(item["display_name"], "実利用者")
        self.assertEqual(item["visit_count"], 1)
        self.assertEqual(item["nomination_labels"], ["本指名"])
        self.assertNotIn("phone", item)
        self.assertNotIn("staff_memo", item)

    def test_can_view_history_and_save_private_cast_memo(self):
        order = self.create_done_order()

        saved = self.client.patch(
            f"/api/cast/customers/{self.customer.id}/",
            {"memo": "強めの指圧がお好み"},
            format="json",
        )
        detail = self.client.get(f"/api/cast/customers/{self.customer.id}/")

        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual(detail.status_code, 200, detail.data)
        self.assertEqual(detail.data["memo"], "強めの指圧がお好み")
        self.assertEqual(detail.data["history"][0]["id"], order.id)
        self.assertNotIn("phone", detail.data)
        self.assertNotIn("staff_memo", detail.data)

    def test_other_cast_cannot_read_or_write_customer(self):
        self.create_done_order()

        get_response = self.other_client.get(
            f"/api/cast/customers/{self.customer.id}/",
        )
        patch_response = self.other_client.patch(
            f"/api/cast/customers/{self.customer.id}/",
            {"memo": "見えないメモ"},
            format="json",
        )

        self.assertEqual(get_response.status_code, 404)
        self.assertEqual(patch_response.status_code, 404)

    def test_incomplete_order_does_not_grant_customer_access(self):
        start = timezone.now() + timedelta(days=1)
        Order.objects.create(
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
            status=Order.Status.CONFIRMED,
        )

        response = self.client.get(f"/api/cast/customers/{self.customer.id}/")

        self.assertEqual(response.status_code, 404)
