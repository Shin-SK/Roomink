from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
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


class OffShiftRoomPendingOrderTest(TestCase):
    def setUp(self):
        self.business_date = timezone.localdate() + timedelta(days=2)
        self.store = Store.objects.create(name="シフト外予約テスト店")
        self.room = Room.objects.create(store=self.store, name="101")
        self.other_room = Room.objects.create(store=self.store, name="102")
        self.shift_cast = Cast.objects.create(store=self.store, name="出勤キャスト")
        self.off_shift_cast = Cast.objects.create(store=self.store, name="非出勤キャスト")
        self.customer_user = User.objects.create_user("off_shift_customer")
        self.customer = Customer.objects.create(
            store=self.store,
            user=self.customer_user,
            phone="09011110000",
            display_name="予約顧客",
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
            cast=self.shift_cast,
            room=self.room,
            start_time=time(10, 0),
            end_time=time(18, 0),
        )

        self.manager = self.create_operator("off_shift_manager", UserProfile.Role.MANAGER)
        self.staff = self.create_operator("off_shift_staff", UserProfile.Role.STAFF)
        self.cast_user = self.create_operator("off_shift_cast_user", UserProfile.Role.CAST)
        self.manager_client = self.authenticated_client(self.manager)
        self.staff_client = self.authenticated_client(self.staff)
        self.cast_client = self.authenticated_client(self.cast_user)
        self.customer_client = self.authenticated_client(self.customer_user)

    def create_operator(self, username, role):
        user = User.objects.create_user(username)
        UserProfile.objects.create(user=user, store=self.store, role=role)
        return user

    def authenticated_client(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def at(self, hour, minute=0):
        return datetime.combine(
            self.business_date,
            time(hour, minute),
            tzinfo=TOKYO,
        )

    def order_payload(self, cast=None, hour=12):
        return {
            "customer": self.customer.id,
            "cast": (cast or self.off_shift_cast).id,
            "course": self.course.id,
            "start": self.at(hour).isoformat(),
        }

    def create_pending_order(self, hour=12, status=Order.Status.CONFIRMED):
        return Order.objects.create(
            store=self.store,
            cast=self.off_shift_cast,
            room=None,
            customer=self.customer,
            course=self.course,
            course_name=self.course.name,
            course_price=self.course.price,
            total_price=self.course.price,
            start=self.at(hour),
            end=self.at(hour + 1),
            status=status,
        )

    def test_manager_and_staff_can_create_off_shift_order_with_room_pending(self):
        manager_response = self.manager_client.post(
            "/api/orders/", self.order_payload(hour=12), format="json",
        )
        staff_response = self.staff_client.post(
            "/api/orders/", self.order_payload(hour=14), format="json",
        )

        self.assertEqual(manager_response.status_code, 201, manager_response.data)
        self.assertEqual(staff_response.status_code, 201, staff_response.data)
        self.assertIsNone(manager_response.data["room"])
        self.assertEqual(manager_response.data["room_name"], "")
        self.assertTrue(manager_response.data["is_off_shift"])
        self.assertTrue(manager_response.data["is_room_pending"])
        self.assertIsNone(Order.objects.get(pk=manager_response.data["id"]).room_id)

    def test_cast_and_customer_cannot_create_off_shift_order(self):
        cast_response = self.cast_client.post(
            "/api/orders/", self.order_payload(hour=12), format="json",
        )
        customer_response = self.customer_client.post(
            "/api/orders/", self.order_payload(hour=14), format="json",
        )
        customer_booking_response = self.customer_client.post(
            "/api/cu/bookings/",
            {
                "cast": self.off_shift_cast.id,
                "course": self.course.id,
                "start": self.at(16).isoformat(),
            },
            format="json",
        )

        self.assertEqual(cast_response.status_code, 403, cast_response.data)
        self.assertEqual(customer_response.status_code, 403, customer_response.data)
        self.assertEqual(
            customer_booking_response.status_code,
            403,
            customer_booking_response.data,
        )
        self.assertEqual(Order.objects.count(), 0)

    def test_on_shift_order_keeps_room_auto_assignment(self):
        response = self.manager_client.post(
            "/api/orders/",
            self.order_payload(cast=self.shift_cast, hour=12),
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["room"], self.room.id)
        self.assertFalse(response.data["is_off_shift"])
        self.assertFalse(response.data["is_room_pending"])

    def test_off_shift_order_still_rejects_cast_conflict(self):
        self.create_pending_order(hour=12)

        response = self.manager_client.post(
            "/api/orders/", self.order_payload(hour=12), format="json",
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(Order.objects.count(), 1)

    def test_off_shift_order_can_be_confirmed_and_cast_and_customer_views_are_safe(self):
        self.off_shift_cast.user = self.cast_user
        self.off_shift_cast.save(update_fields=["user"])
        created = self.manager_client.post(
            "/api/orders/", self.order_payload(hour=12), format="json",
        )

        confirmed = self.manager_client.post(f"/api/orders/{created.data['id']}/confirm/")
        cast_today = self.cast_client.get(
            f"/api/cast/today/?date={self.business_date.isoformat()}"
        )
        customer_detail = self.customer_client.get(
            f"/api/cu/reservations/{created.data['id']}/"
        )

        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        self.assertTrue(confirmed.data["is_room_pending"])
        self.assertEqual(cast_today.status_code, 200, cast_today.data)
        self.assertTrue(cast_today.data["orders"][0]["is_room_pending"])
        self.assertEqual(cast_today.data["orders"][0]["room_name"], "")
        self.assertEqual(customer_detail.status_code, 200, customer_detail.data)
        self.assertEqual(customer_detail.data["room_name"], "")
        self.assertEqual(customer_detail.data["room_address"], "")

    def test_off_shift_order_can_be_extended_while_room_is_pending(self):
        pending = self.create_pending_order()

        response = self.manager_client.post(
            f"/api/orders/{pending.id}/apply_extension/",
            {"extension_id": None, "extension_duration": 30, "extension_price": 3000},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        pending.refresh_from_db()
        self.assertIsNone(pending.room_id)
        self.assertEqual(pending.end, self.at(13, 30))
        self.assertEqual(pending.extension_duration, 30)

    def test_schedule_lists_shift_cast_first_and_marks_off_shift_cast_and_order(self):
        pending = self.create_pending_order()

        response = self.manager_client.get(
            f"/api/op/schedule/?date={self.business_date.isoformat()}"
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            [item["id"] for item in response.data["casts"]],
            [self.shift_cast.id, self.off_shift_cast.id],
        )
        self.assertFalse(response.data["casts"][0]["is_off_shift"])
        self.assertTrue(response.data["casts"][1]["is_off_shift"])
        serialized_order = next(item for item in response.data["orders"] if item["id"] == pending.id)
        self.assertIsNone(serialized_order["room_id"])
        self.assertTrue(serialized_order["is_off_shift"])
        self.assertTrue(serialized_order["is_room_pending"])

    def test_covering_shift_assigns_room_to_pending_order(self):
        pending = self.create_pending_order()

        response = self.manager_client.post(
            "/api/shifts/",
            {
                "date": self.business_date.isoformat(),
                "cast": self.off_shift_cast.id,
                "room": self.other_room.id,
                "start_time": "11:00",
                "end_time": "18:00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["assigned_order_count"], 1)
        pending.refresh_from_db()
        self.assertEqual(pending.room, self.other_room)

    def test_partial_shift_and_room_conflict_do_not_assign_pending_order(self):
        pending = self.create_pending_order()

        partial = self.manager_client.post(
            "/api/shifts/",
            {
                "date": self.business_date.isoformat(),
                "cast": self.off_shift_cast.id,
                "room": self.other_room.id,
                "start_time": "12:30",
                "end_time": "18:00",
            },
            format="json",
        )
        self.assertEqual(partial.status_code, 400, partial.data)

        Order.objects.create(
            store=self.store,
            cast=self.shift_cast,
            room=self.other_room,
            customer=self.customer,
            course=self.course,
            course_name=self.course.name,
            course_price=self.course.price,
            total_price=self.course.price,
            start=self.at(12),
            end=self.at(13),
            status=Order.Status.CONFIRMED,
        )
        room_conflict = self.manager_client.post(
            "/api/shifts/",
            {
                "date": self.business_date.isoformat(),
                "cast": self.off_shift_cast.id,
                "room": self.other_room.id,
                "start_time": "11:00",
                "end_time": "18:00",
            },
            format="json",
        )

        self.assertEqual(room_conflict.status_code, 400, room_conflict.data)
        pending.refresh_from_db()
        self.assertIsNone(pending.room_id)
        self.assertFalse(ShiftAssignment.objects.filter(cast=self.off_shift_cast).exists())

    def test_shift_with_active_order_cannot_be_deleted(self):
        shift = ShiftAssignment.objects.get(cast=self.shift_cast)
        Order.objects.create(
            store=self.store,
            cast=self.shift_cast,
            room=self.room,
            customer=self.customer,
            course=self.course,
            course_name=self.course.name,
            course_price=self.course.price,
            total_price=self.course.price,
            start=self.at(12),
            end=self.at(13),
            status=Order.Status.CONFIRMED,
        )

        response = self.manager_client.delete(f"/api/shifts/{shift.id}/")

        self.assertEqual(response.status_code, 400, response.data)
        self.assertTrue(ShiftAssignment.objects.filter(pk=shift.id).exists())
