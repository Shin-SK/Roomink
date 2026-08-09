from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Cast, Course, Customer, Order, Room, Store, UserProfile


User = get_user_model()


class RoomAddressCustomerPageTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="住所表示テスト店舗")
        self.manager = User.objects.create_user("address_manager", password="pass")
        UserProfile.objects.create(
            user=self.manager,
            store=self.store,
            role=UserProfile.Role.MANAGER,
        )
        cast_user = User.objects.create_user("address_cast", password="pass")
        UserProfile.objects.create(
            user=cast_user,
            store=self.store,
            role=UserProfile.Role.CAST,
        )
        self.cast = Cast.objects.create(
            store=self.store,
            user=cast_user,
            name="住所表示キャスト",
        )
        self.room = Room.objects.create(store=self.store, name="101")
        self.course = Course.objects.create(
            store=self.store,
            name="60分",
            duration=60,
            price=10000,
        )

        self.customer_user = User.objects.create_user("address_customer", password="pass")
        self.customer = Customer.objects.create(
            store=self.store,
            user=self.customer_user,
            phone="09011112222",
            display_name="住所表示顧客",
        )
        other_user = User.objects.create_user("other_address_customer", password="pass")
        self.other_customer = Customer.objects.create(
            store=self.store,
            user=other_user,
            phone="09033334444",
            display_name="別顧客",
        )

        start = timezone.now() + timedelta(days=1)
        self.confirmed_order = self.create_order(
            self.customer,
            start,
            Order.Status.CONFIRMED,
        )
        self.requested_order = self.create_order(
            self.customer,
            start + timedelta(hours=2),
            Order.Status.REQUESTED,
        )

        self.manager_client = APIClient()
        self.manager_client.force_authenticate(self.manager)
        self.customer_client = APIClient()
        self.customer_client.force_authenticate(self.customer_user)
        self.other_customer_client = APIClient()
        self.other_customer_client.force_authenticate(other_user)

    def create_order(self, customer, start, status):
        return Order.objects.create(
            store=self.store,
            cast=self.cast,
            room=self.room,
            customer=customer,
            course=self.course,
            course_name=self.course.name,
            course_price=self.course.price,
            total_price=self.course.price,
            start=start,
            end=start + timedelta(hours=1),
            status=status,
        )

    def set_room_address(self):
        response = self.manager_client.patch(
            f"/api/rooms/{self.room.id}/",
            {"address": "東京都新宿区テスト1-2-3 テストビル101"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        return response

    def test_manager_can_save_room_address(self):
        response = self.set_room_address()

        self.assertEqual(response.data["address"], "東京都新宿区テスト1-2-3 テストビル101")
        self.room.refresh_from_db()
        self.assertEqual(self.room.address, "東京都新宿区テスト1-2-3 テストビル101")

    def test_confirmed_customer_reservation_returns_room_address(self):
        self.set_room_address()

        detail = self.customer_client.get(
            f"/api/cu/reservations/{self.confirmed_order.id}/"
        )
        mypage = self.customer_client.get("/api/cu/mypage/")

        self.assertEqual(detail.status_code, 200, detail.data)
        self.assertEqual(
            detail.data["room_address"],
            "東京都新宿区テスト1-2-3 テストビル101",
        )
        self.assertEqual(mypage.status_code, 200, mypage.data)
        self.assertEqual(
            mypage.data["next_reservation"]["room_address"],
            "東京都新宿区テスト1-2-3 テストビル101",
        )

    def test_address_is_hidden_before_confirmation_and_from_other_customer(self):
        self.set_room_address()

        requested = self.customer_client.get(
            f"/api/cu/reservations/{self.requested_order.id}/"
        )
        other_customer = self.other_customer_client.get(
            f"/api/cu/reservations/{self.confirmed_order.id}/"
        )

        self.assertEqual(requested.status_code, 200, requested.data)
        self.assertEqual(requested.data["room_address"], "")
        self.assertEqual(other_customer.status_code, 404, other_customer.data)
