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

    def test_searches_only_by_visible_customer_name(self):
        self.create_done_order()

        found = self.client.get("/api/cast/customers/?q=実利用")
        hidden = self.client.get("/api/cast/customers/?q=0901111")

        self.assertEqual(len(found.data["customers"]), 1)
        self.assertEqual(hidden.data["customers"], [])

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

    def test_other_store_customer_is_not_accessible(self):
        self.create_done_order()
        other_store = Store.objects.create(name="別店舗")
        other_customer = Customer.objects.create(
            store=other_store,
            display_name="別店舗のお客様",
            phone="09099998888",
        )

        response = self.client.get(f"/api/cast/customers/{other_customer.id}/")

        self.assertEqual(response.status_code, 404)

    def test_confirmed_customer_can_be_searched_and_memoed_before_first_visit(self):
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

        response = self.client.get("/api/cast/customers/?q=実利用")
        item = response.data["customers"][0]
        self.assertEqual(item["id"], self.customer.id)
        self.assertEqual(item["visit_count"], 0)
        self.assertIsNone(item["last_visit_at"])
        self.assertIsNotNone(item["next_booking_at"])
        self.assertEqual(item["nomination_labels"], [])
        detail = self.client.get(f"/api/cast/customers/{self.customer.id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["history"], [])
        saved = self.client.patch(
            f"/api/cast/customers/{self.customer.id}/", {"memo": "初回接客前のメモ"}, format="json",
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.data["memo"], "初回接客前のメモ")

    def test_access_tracks_status_assignment_and_keeps_completed_counts(self):
        order = self.create_done_order()
        for status in Order.Status.values:
            with self.subTest(status=status):
                Order.objects.filter(pk=order.pk).update(status=status)
                allowed = status in (Order.Status.CONFIRMED, Order.Status.IN_PROGRESS,
                                     Order.Status.PENDING_FINALIZE, Order.Status.DONE)
                listing = self.client.get("/api/cast/customers/").data["customers"]
                self.assertEqual(len(listing), int(allowed))
                detail = self.client.get(f"/api/cast/customers/{self.customer.id}/")
                self.assertEqual(detail.status_code, 200 if allowed else 404)
                saved = self.client.patch(f"/api/cast/customers/{self.customer.id}/",
                                          {"memo": "状態確認"}, format="json")
                self.assertEqual(saved.status_code, 200 if allowed else 404)
                if allowed:
                    self.assertEqual(listing[0]["visit_count"], int(status == Order.Status.DONE))
                    self.assertEqual(len(detail.data["history"]), int(status == Order.Status.DONE))
        Order.objects.filter(pk=order.pk).update(status=Order.Status.CONFIRMED, cast=self.other_cast)
        self.assertEqual(self.client.get("/api/cast/customers/").data["customers"], [])
        self.assertEqual(self.client.get(f"/api/cast/customers/{self.customer.id}/").status_code, 404)
        self.assertEqual(self.other_client.get(f"/api/cast/customers/{self.customer.id}/").status_code, 200)
        self.assertEqual(self.other_client.get(f"/api/cast/customers/{self.customer.id}/").data["memo"], "")

    def test_confirmed_recipient_not_contact_is_visible_and_history_survives_cancellation(self):
        done = self.create_done_order(customer=self.contact, recipient=self.customer)
        upcoming = self.create_done_order(customer=self.contact, recipient=self.customer, days_ago=-1)
        Order.objects.filter(pk=upcoming.pk).update(status=Order.Status.CONFIRMED)
        item = self.client.get("/api/cast/customers/").data["customers"][0]
        self.assertEqual(item["id"], self.customer.pk)
        self.assertEqual(item["visit_count"], 1)
        self.assertEqual(item["last_visit_at"], done.start)
        self.assertEqual(item["next_booking_at"], upcoming.start)
        self.assertEqual(self.client.get(f"/api/cast/customers/{self.contact.pk}/").status_code, 404)
        Order.objects.filter(pk=upcoming.pk).update(status=Order.Status.CANCELLED)
        item = self.client.get("/api/cast/customers/").data["customers"][0]
        self.assertEqual(item["visit_count"], 1)
        self.assertIsNone(item["next_booking_at"])

    def test_rejects_non_string_and_too_long_memos(self):
        self.create_done_order()

        invalid_type = self.client.patch(
            f"/api/cast/customers/{self.customer.id}/",
            {"memo": ["invalid"]},
            format="json",
        )
        too_long = self.client.patch(
            f"/api/cast/customers/{self.customer.id}/",
            {"memo": "a" * 2001},
            format="json",
        )

        self.assertEqual(invalid_type.status_code, 400)
        self.assertEqual(too_long.status_code, 400)
