from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Cast, Course, Customer, Order, Room, ShiftAssignment, Store, UserProfile


User = get_user_model()


class OrderOperatorTrackingTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="予約操作記録テスト店")
        self.manager = self.create_operator("tracking_manager", UserProfile.Role.MANAGER)
        self.staff = self.create_operator("tracking_staff", UserProfile.Role.STAFF)
        self.cast = Cast.objects.create(store=self.store, name="記録キャスト")
        self.room = Room.objects.create(store=self.store, name="記録ルーム")
        self.customer = Customer.objects.create(
            store=self.store,
            phone="09000001111",
            display_name="記録顧客",
        )
        self.course = Course.objects.create(
            store=self.store,
            name="60分",
            duration=60,
            price=10000,
        )
        self.start = (timezone.now() + timedelta(days=1)).replace(
            hour=18,
            minute=0,
            second=0,
            microsecond=0,
        )
        ShiftAssignment.objects.create(
            store=self.store,
            date=timezone.localtime(self.start).date(),
            cast=self.cast,
            room=self.room,
            start_time=timezone.localtime(self.start).time(),
            end_time=(timezone.localtime(self.start) + timedelta(hours=4)).time(),
        )

    def create_operator(self, username, role):
        user = User.objects.create_user(username=username, password="operator-pass")
        UserProfile.objects.create(user=user, store=self.store, role=role)
        return user

    def client_as(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def create_order(self):
        response = self.client_as(self.staff).post(
            "/api/orders/",
            {
                "cast": self.cast.pk,
                "customer": self.customer.pk,
                "course": self.course.pk,
                "start": self.start.isoformat(),
                "end": (self.start + timedelta(hours=1)).isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        return Order.objects.get(pk=response.data["id"])

    def test_create_update_and_cancel_operators_are_recorded(self):
        order = self.create_order()
        self.assertEqual(order.created_by, self.staff)
        self.assertEqual(order.updated_by, self.staff)
        self.assertIsNone(order.cancelled_by)

        update_response = self.client_as(self.manager).patch(
            f"/api/orders/{order.pk}/",
            {"memo": "管理者が修正"},
            format="json",
        )
        self.assertEqual(update_response.status_code, 200, update_response.data)

        cancel_response = self.client_as(self.staff).post(
            f"/api/orders/{order.pk}/cancel/",
            {},
            format="json",
        )
        self.assertEqual(cancel_response.status_code, 200, cancel_response.data)

        order.refresh_from_db()
        self.assertEqual(order.created_by, self.staff)
        self.assertEqual(order.updated_by, self.staff)
        self.assertEqual(order.cancelled_by, self.staff)
        self.assertEqual(cancel_response.data["created_by_name"], "tracking_staff")
        self.assertEqual(cancel_response.data["updated_by_name"], "tracking_staff")
        self.assertEqual(cancel_response.data["cancelled_by_name"], "tracking_staff")
