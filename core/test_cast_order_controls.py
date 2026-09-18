from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import (
    Cast,
    CastAck,
    Course,
    Customer,
    Option,
    Order,
    Room,
    Store,
    UserProfile,
)
from core.services.business_datetime import business_date_for_datetime


User = get_user_model()


class CastOrderControlsTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(
            name="セラピスト予約操作テスト店",
            timezone="Asia/Tokyo",
        )
        self.other_store = Store.objects.create(name="別店舗", timezone="Asia/Tokyo")
        self.cast_user = self._user("cast_controls", self.store, UserProfile.Role.CAST)
        self.other_cast_user = self._user(
            "other_cast_controls",
            self.store,
            UserProfile.Role.CAST,
        )
        self.cast = Cast.objects.create(
            store=self.store,
            user=self.cast_user,
            name="担当セラピスト",
            course_back_rate=50,
            option_back_rate=100,
        )
        self.other_cast = Cast.objects.create(
            store=self.store,
            user=self.other_cast_user,
            name="別セラピスト",
        )
        self.room = Room.objects.create(store=self.store, name="高田馬場A")
        self.customer = Customer.objects.create(
            store=self.store,
            phone="09000000000",
            display_name="連絡者名",
        )
        self.course = Course.objects.create(
            store=self.store,
            name="スタンダード90分",
            duration=90,
            price=17000,
        )
        self.option_a = Option.objects.create(
            store=self.store,
            name="衣装チェンジ",
            price=4000,
        )
        self.option_b = Option.objects.create(
            store=self.store,
            name="ディープリンパ",
            price=2000,
        )
        self.foreign_option = Option.objects.create(
            store=self.other_store,
            name="別店舗オプション",
            price=9999,
        )
        start = timezone.now().replace(second=0, microsecond=0)
        self.order = Order.objects.create(
            store=self.store,
            cast=self.cast,
            room=self.room,
            customer=self.customer,
            service_recipient_name="予約名テスト",
            course=self.course,
            course_name=self.course.name,
            course_price=self.course.price,
            options_price=self.option_a.price,
            total_price=self.course.price + self.option_a.price,
            start=start,
            end=start + timedelta(minutes=90),
            status=Order.Status.CONFIRMED,
            payment_method=Order.PaymentMethod.CASH,
        )
        self.order.options.add(self.option_a)
        self.cast_client = self._client(self.cast_user)
        self.other_cast_client = self._client(self.other_cast_user)

    def _user(self, username, store, role):
        user = User.objects.create_user(username, password="pass")
        UserProfile.objects.create(user=user, store=store, role=role)
        return user

    def _client(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_today_response_contains_reservation_payment_and_option_details(self):
        business_date = business_date_for_datetime(self.order.start, self.store.timezone)

        response = self.cast_client.get(f"/api/cast/today/?date={business_date.isoformat()}")

        self.assertEqual(response.status_code, 200, response.data)
        item = response.data["orders"][0]
        self.assertEqual(item["reservation_name"], "予約名テスト")
        self.assertEqual(item["payment_method"], Order.PaymentMethod.CASH)
        self.assertEqual(item["payment_method_label"], "現金")
        self.assertEqual(item["option_ids"], [self.option_a.id])
        self.assertEqual(item["options"][0]["name"], "衣装チェンジ")
        self.assertEqual(item["total_price"], 21000)
        available_ids = {option["id"] for option in response.data["available_options"]}
        self.assertEqual(available_ids, {self.option_a.id, self.option_b.id})

    def test_cast_can_change_options_and_total_is_recalculated(self):
        response = self.cast_client.post(
            f"/api/cast/orders/{self.order.id}/options/",
            {"option_ids": [self.option_b.id]},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.order.refresh_from_db()
        self.assertEqual(list(self.order.options.values_list("id", flat=True)), [self.option_b.id])
        self.assertEqual(self.order.options_price, 2000)
        self.assertEqual(self.order.total_price, 19000)
        self.assertEqual(self.order.updated_by_id, self.cast_user.id)
        self.assertEqual(response.data["option_ids"], [self.option_b.id])
        self.assertEqual(response.data["total_price"], 19000)

    def test_option_from_another_store_is_rejected_without_changes(self):
        response = self.cast_client.post(
            f"/api/cast/orders/{self.order.id}/options/",
            {"option_ids": [self.foreign_option.id]},
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.order.refresh_from_db()
        self.assertEqual(list(self.order.options.values_list("id", flat=True)), [self.option_a.id])
        self.assertEqual(self.order.total_price, 21000)

    def test_cast_ack_start_and_complete_reflects_sales_and_salary(self):
        ack_response = self.cast_client.post(f"/api/cast/orders/{self.order.id}/ack/")
        start_response = self.cast_client.post(f"/api/cast/orders/{self.order.id}/start/")
        complete_response = self.cast_client.post(f"/api/cast/orders/{self.order.id}/complete/")
        sales_response = self.cast_client.get("/api/cast/today-sales/")

        self.assertEqual(ack_response.status_code, 200, ack_response.data)
        self.assertEqual(start_response.status_code, 200, start_response.data)
        self.assertEqual(start_response.data["status"], Order.Status.IN_PROGRESS)
        self.assertEqual(complete_response.status_code, 200, complete_response.data)
        self.assertEqual(complete_response.data["status"], Order.Status.DONE)
        self.assertEqual(sales_response.status_code, 200, sales_response.data)
        self.assertEqual(sales_response.data["done_count"], 1)
        self.assertEqual(sales_response.data["total_sales"], 21000)
        self.assertEqual(sales_response.data["estimated_pay"], 12500)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.DONE)
        self.assertEqual(self.order.updated_by_id, self.cast_user.id)

    def test_start_requires_ack_and_complete_requires_payment_method(self):
        start_response = self.cast_client.post(f"/api/cast/orders/{self.order.id}/start/")
        self.assertEqual(start_response.status_code, 400, start_response.data)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CONFIRMED)

        CastAck.objects.create(order=self.order, acked_at=timezone.now())
        self.order.status = Order.Status.IN_PROGRESS
        self.order.payment_method = Order.PaymentMethod.UNSET
        self.order.save(update_fields=["status", "payment_method", "updated_at"])
        complete_response = self.cast_client.post(
            f"/api/cast/orders/{self.order.id}/complete/",
        )

        self.assertEqual(complete_response.status_code, 400, complete_response.data)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.IN_PROGRESS)

    def test_other_cast_cannot_change_or_advance_order(self):
        CastAck.objects.create(order=self.order, acked_at=timezone.now())
        requests = [
            ("options", {"option_ids": [self.option_b.id]}),
            ("start", {}),
            ("complete", {}),
        ]

        for action, payload in requests:
            with self.subTest(action=action):
                response = self.other_cast_client.post(
                    f"/api/cast/orders/{self.order.id}/{action}/",
                    payload,
                    format="json",
                )
                self.assertEqual(response.status_code, 403, response.data)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CONFIRMED)
        self.assertEqual(list(self.order.options.values_list("id", flat=True)), [self.option_a.id])

    def test_confirmed_card_payment_blocks_cast_option_changes(self):
        self.order.payment_method = Order.PaymentMethod.CARD
        self.order.card_include_options = True
        self.order.card_payment_confirmed_at = timezone.now()
        self.order.save(update_fields=[
            "payment_method",
            "card_include_options",
            "card_payment_confirmed_at",
            "updated_at",
        ])

        response = self.cast_client.post(
            f"/api/cast/orders/{self.order.id}/options/",
            {"option_ids": [self.option_b.id]},
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("カード決済確認済み", response.data["detail"])
        self.order.refresh_from_db()
        self.assertEqual(list(self.order.options.values_list("id", flat=True)), [self.option_a.id])

    def test_card_payment_pending_is_visible_and_cannot_start_service(self):
        self.order.payment_method = Order.PaymentMethod.CARD
        self.order.save(update_fields=["payment_method", "updated_at"])
        CastAck.objects.create(order=self.order, acked_at=timezone.now())
        business_date = business_date_for_datetime(self.order.start, self.store.timezone)

        today = self.cast_client.get(f"/api/cast/today/?date={business_date.isoformat()}")
        start = self.cast_client.post(f"/api/cast/orders/{self.order.id}/start/")

        self.assertEqual(today.status_code, 200, today.data)
        self.assertEqual(today.data["orders"][0]["customer_reservation_state"], "PAYMENT_REQUIRED")
        self.assertEqual(start.status_code, 400, start.data)
        self.assertIn("本予約", start.data["detail"])
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CONFIRMED)
