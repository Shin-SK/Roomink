from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import (
    Cast, CastCustomerMemo, Course, Customer, Order, Room, Store, UserProfile,
)


User = get_user_model()


class CustomerReservationContextTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="受付履歴テスト店", timezone="Asia/Tokyo")
        self.other_store = Store.objects.create(name="別店舗", timezone="Asia/Tokyo")
        self.user = User.objects.create_user("reservation_context_manager", password="pass")
        UserProfile.objects.create(
            user=self.user,
            store=self.store,
            role=UserProfile.Role.MANAGER,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.cast = Cast.objects.create(store=self.store, name="利用ありキャスト")
        self.ng_cast = Cast.objects.create(store=self.store, name="個別NGキャスト")
        self.other_cast = Cast.objects.create(store=self.other_store, name="別店舗キャスト")
        self.room = Room.objects.create(store=self.store, name="101")
        self.course = Course.objects.create(
            store=self.store,
            name="90分",
            duration=90,
            price=18000,
        )
        self.customer = Customer.objects.create(
            store=self.store,
            phone="09000000001",
            display_name="受付履歴顧客",
            flag=Customer.Flag.BAN,
            ban_type=Customer.BanType.CAST_NG,
            online_booking_ng=True,
            staff_memo="受付前に担当を確認",
        )
        self.customer.ng_casts.add(self.ng_cast)

    def create_order(self, *, status, cast=None, customer=None, recipient=None, nomination=""):
        start = timezone.now() - timedelta(days=3)
        return Order.objects.create(
            store=self.store,
            cast=cast or self.cast,
            room=self.room,
            customer=customer or self.customer,
            service_recipient_customer=recipient,
            course=self.course,
            course_name=self.course.name,
            course_price=self.course.price,
            nomination_fee_name=nomination,
            total_price=self.course.price,
            start=start,
            end=start + timedelta(minutes=90),
            status=status,
        )

    def test_context_returns_completed_usage_nomination_and_restrictions(self):
        self.create_order(status=Order.Status.DONE, nomination="本指名")
        self.create_order(status=Order.Status.DONE, nomination="本指名")
        self.create_order(status=Order.Status.CANCELLED, nomination="本指名")
        self.create_order(status=Order.Status.CONFIRMED)

        response = self.client.get(
            f"/api/customers/{self.customer.id}/reservation-context/",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["staff_memo"], "受付前に担当を確認")
        self.assertTrue(response.data["restrictions"]["individual_cast_ng"])
        self.assertTrue(response.data["restrictions"]["online_booking_ng"])
        self.assertEqual(
            response.data["restrictions"]["ng_casts"],
            [{"id": self.ng_cast.id, "name": self.ng_cast.name}],
        )
        self.assertEqual(response.data["cast_history"][0]["cast_id"], self.cast.id)
        self.assertEqual(response.data["cast_history"][0]["visit_count"], 2)
        self.assertEqual(response.data["cast_history"][0]["nomination_labels"], ["本指名"])

    def test_service_recipient_history_is_counted_once(self):
        contact = Customer.objects.create(
            store=self.store,
            phone="09000000002",
            display_name="連絡者",
        )
        self.create_order(
            status=Order.Status.DONE,
            customer=contact,
            recipient=self.customer,
        )

        response = self.client.get(
            f"/api/customers/{self.customer.id}/reservation-context/",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["cast_history"][0]["visit_count"], 1)

    def test_other_store_customer_is_not_disclosed(self):
        other_customer = Customer.objects.create(
            store=self.other_store,
            phone="09000000003",
        )

        response = self.client.get(
            f"/api/customers/{other_customer.id}/reservation-context/",
        )

        self.assertEqual(response.status_code, 404)

    def test_rejects_ng_cast_from_another_store(self):
        response = self.client.patch(
            f"/api/customers/{self.customer.id}/",
            {"ng_casts": [self.other_cast.id]},
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("ng_casts", response.data)
        self.assertEqual(
            list(self.customer.ng_casts.values_list("id", flat=True)),
            [self.ng_cast.id],
        )

    def test_create_rejects_ng_cast_from_another_store(self):
        response = self.client.post(
            "/api/customers/",
            {
                "phone": "09000000005",
                "display_name": "新規顧客",
                "flag": Customer.Flag.BAN,
                "ban_type": Customer.BanType.CAST_NG,
                "ng_casts": [self.other_cast.id],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("ng_casts", response.data)

    def test_store_ng_is_reported_separately(self):
        self.customer.ban_type = Customer.BanType.STORE_BAN
        self.customer.save(update_fields=["ban_type"])
        self.customer.ng_casts.clear()

        response = self.client.get(
            f"/api/customers/{self.customer.id}/reservation-context/",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["restrictions"]["store_ng"])
        self.assertFalse(response.data["restrictions"]["individual_cast_ng"])

    def test_merge_preserves_online_and_individual_cast_ng_settings(self):
        keep = Customer.objects.create(
            store=self.store,
            phone="09000000004",
            display_name="統合先顧客",
        )
        CastCustomerMemo.objects.create(
            cast=self.cast,
            customer=keep,
            memo="統合先メモ",
        )
        CastCustomerMemo.objects.create(
            cast=self.cast,
            customer=self.customer,
            memo="統合元メモ",
        )
        response = self.client.post(
            f"/api/customers/{keep.id}/merge/",
            {"merge_id": self.customer.id},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        keep.refresh_from_db()
        self.assertEqual(keep.flag, Customer.Flag.BAN)
        self.assertEqual(keep.ban_type, Customer.BanType.CAST_NG)
        self.assertTrue(keep.online_booking_ng)
        self.assertEqual(
            list(keep.ng_casts.values_list("id", flat=True)),
            [self.ng_cast.id],
        )
        self.assertEqual(
            CastCustomerMemo.objects.get(cast=self.cast, customer=keep).memo,
            "統合先メモ\n\n統合元メモ",
        )
