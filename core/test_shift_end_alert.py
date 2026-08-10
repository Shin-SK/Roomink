from datetime import date, datetime, time
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import TestCase
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


class ShiftEndAlertTest(TestCase):
    def setUp(self):
        self.business_date = date(2026, 8, 16)
        self.store = Store.objects.create(name="70分前アラート店", timezone="Asia/Tokyo")
        self.room = Room.objects.create(store=self.store, name="101")
        self.cast = Cast.objects.create(store=self.store, name="終了確認キャスト")
        self.customer = Customer.objects.create(
            store=self.store,
            phone="09011112222",
            display_name="予約者",
        )
        self.course = Course.objects.create(
            store=self.store,
            name="60分",
            duration=60,
            price=10000,
        )
        self.shift = ShiftAssignment.objects.create(
            store=self.store,
            date=self.business_date,
            cast=self.cast,
            room=self.room,
            start_time=time(18, 0),
            end_time=time(22, 0),
        )

        self.manager = self.create_operator("alert_manager", UserProfile.Role.MANAGER)
        self.staff = self.create_operator("alert_staff", UserProfile.Role.STAFF)
        self.cast_user = self.create_operator("alert_cast", UserProfile.Role.CAST)
        self.customer_user = User.objects.create_user("alert_customer")
        self.customer.user = self.customer_user
        self.customer.save(update_fields=["user"])

        self.manager_client = self.authenticated_client(self.manager)
        self.staff_client = self.authenticated_client(self.staff)
        self.cast_client = self.authenticated_client(self.cast_user)
        self.customer_client = self.authenticated_client(self.customer_user)

    def create_operator(self, username, role, store=None):
        user = User.objects.create_user(username)
        UserProfile.objects.create(
            user=user,
            store=store or self.store,
            role=role,
        )
        return user

    def authenticated_client(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def at(self, day, hour, minute=0):
        return datetime(2026, 8, day, hour, minute, tzinfo=TOKYO)

    def fetch(self, reference_at, client=None):
        with patch("django.utils.timezone.now", return_value=reference_at):
            return (client or self.manager_client).get("/api/op/shift-end-alerts/")

    def create_order(
        self,
        start,
        end,
        status=Order.Status.CONFIRMED,
        total_price=10000,
    ):
        return Order.objects.create(
            store=self.store,
            cast=self.cast,
            room=self.room,
            customer=self.customer,
            course=self.course,
            course_name=self.course.name,
            course_price=total_price,
            total_price=total_price,
            start=start,
            end=end,
            status=status,
        )

    def alert_model(self):
        return apps.get_model("core", "ShiftEndAlert")

    def test_alert_opens_exactly_70_minutes_before_shift_end(self):
        before = self.fetch(self.at(16, 20, 49))
        at_alert = self.fetch(self.at(16, 20, 50))

        self.assertEqual(before.status_code, 200, before.data)
        self.assertEqual(before.data["open_alerts"], [])
        self.assertEqual(at_alert.status_code, 200, at_alert.data)
        self.assertEqual(len(at_alert.data["open_alerts"]), 1)
        alert = at_alert.data["open_alerts"][0]
        self.assertEqual(alert["shift_id"], self.shift.id)
        self.assertEqual(alert["cast_name"], self.cast.name)
        self.assertEqual(alert["shift_end_time_extended"], "22:00")
        self.assertEqual(alert["alert_at"], self.at(16, 20, 50).isoformat())
        self.assertEqual(alert["status"], "OPEN")
        self.assertEqual(self.alert_model().objects.count(), 1)

    def test_order_overlapping_alert_window_prevents_alert(self):
        self.create_order(self.at(16, 20, 30), self.at(16, 21, 30))

        response = self.fetch(self.at(16, 20, 50))

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["open_alerts"], [])
        self.assertEqual(self.alert_model().objects.count(), 0)

    def test_interval_boundaries_and_cancelled_order(self):
        cases = (
            (self.at(16, 19, 50), self.at(16, 20, 50), Order.Status.CONFIRMED, True),
            (self.at(16, 22, 0), self.at(16, 23, 0), Order.Status.CONFIRMED, True),
            (self.at(16, 20, 50), self.at(16, 21, 50), Order.Status.REQUESTED, False),
            (self.at(16, 20, 30), self.at(16, 21, 30), Order.Status.DONE, False),
            (self.at(16, 20, 30), self.at(16, 21, 30), Order.Status.CANCELLED, True),
        )
        for start, end, status, should_alert in cases:
            with self.subTest(start=start, end=end, status=status):
                Order.objects.all().delete()
                self.alert_model().objects.all().delete()
                self.create_order(start, end, status=status)

                response = self.fetch(self.at(16, 20, 50))

                self.assertEqual(bool(response.data["open_alerts"]), should_alert)

    def test_open_alert_is_resolved_and_reopened_without_duplicate(self):
        opened = self.fetch(self.at(16, 20, 50))
        alert_id = opened.data["open_alerts"][0]["id"]
        order = self.create_order(
            self.at(16, 20, 30),
            self.at(16, 21, 30),
            status=Order.Status.REQUESTED,
        )

        resolved = self.fetch(self.at(16, 20, 55))

        self.assertEqual(resolved.data["open_alerts"], [])
        self.assertEqual(len(resolved.data["resolved_alerts"]), 1)
        self.assertEqual(resolved.data["resolved_alerts"][0]["id"], alert_id)
        self.assertEqual(resolved.data["resolved_alerts"][0]["status"], "RESOLVED")
        self.assertEqual(self.alert_model().objects.count(), 1)

        order.status = Order.Status.CANCELLED
        order.save(update_fields=["status"])
        reopened = self.fetch(self.at(16, 21, 0))

        self.assertEqual(reopened.data["open_alerts"][0]["id"], alert_id)
        self.assertEqual(reopened.data["resolved_alerts"], [])
        self.assertEqual(self.alert_model().objects.count(), 1)

    def test_response_includes_valid_order_count_and_done_sales(self):
        self.create_order(
            self.at(16, 18, 30),
            self.at(16, 19, 30),
            status=Order.Status.DONE,
            total_price=12000,
        )
        self.create_order(
            self.at(16, 19, 30),
            self.at(16, 20, 30),
            status=Order.Status.CANCELLED,
            total_price=9000,
        )

        response = self.fetch(self.at(16, 20, 50))

        alert = response.data["open_alerts"][0]
        self.assertEqual(alert["valid_order_count"], 1)
        self.assertEqual(alert["done_sales"], 12000)

    def test_extended_shift_ending_at_29_uses_next_day_alert_time(self):
        self.shift.end_time = time(5, 0)
        self.shift.end_day_offset = 1
        self.shift.save(update_fields=["end_time", "end_day_offset"])

        before = self.fetch(self.at(17, 3, 49))
        at_alert = self.fetch(self.at(17, 3, 50))

        self.assertEqual(before.data["open_alerts"], [])
        self.assertEqual(len(at_alert.data["open_alerts"]), 1)
        self.assertEqual(
            at_alert.data["open_alerts"][0]["shift_end_time_extended"],
            "29:00",
        )
        self.assertEqual(
            at_alert.data["open_alerts"][0]["alert_at"],
            self.at(17, 3, 50).isoformat(),
        )

    def test_absent_shift_is_not_alerted(self):
        self.shift.is_absent = True
        self.shift.save(update_fields=["is_absent"])

        response = self.fetch(self.at(16, 20, 50))

        self.assertEqual(response.data["open_alerts"], [])
        self.assertEqual(self.alert_model().objects.count(), 0)

    def test_manager_and_staff_only_and_store_isolation(self):
        other_store = Store.objects.create(name="別店舗", timezone="Asia/Tokyo")
        other_room = Room.objects.create(store=other_store, name="201")
        other_cast = Cast.objects.create(store=other_store, name="別店舗キャスト")
        ShiftAssignment.objects.create(
            store=other_store,
            date=self.business_date,
            cast=other_cast,
            room=other_room,
            start_time=time(18, 0),
            end_time=time(22, 0),
        )
        other_manager = self.create_operator(
            "other_alert_manager",
            UserProfile.Role.MANAGER,
            store=other_store,
        )

        manager_response = self.fetch(self.at(16, 20, 50), self.manager_client)
        staff_response = self.fetch(self.at(16, 20, 50), self.staff_client)
        other_response = self.fetch(
            self.at(16, 20, 50),
            self.authenticated_client(other_manager),
        )
        cast_response = self.fetch(self.at(16, 20, 50), self.cast_client)
        customer_response = self.fetch(self.at(16, 20, 50), self.customer_client)

        self.assertEqual(manager_response.status_code, 200, manager_response.data)
        self.assertEqual(staff_response.status_code, 200, staff_response.data)
        self.assertEqual(
            [item["cast_name"] for item in manager_response.data["open_alerts"]],
            [self.cast.name],
        )
        self.assertEqual(
            [item["cast_name"] for item in other_response.data["open_alerts"]],
            [other_cast.name],
        )
        self.assertEqual(cast_response.status_code, 403, cast_response.data)
        self.assertEqual(customer_response.status_code, 403, customer_response.data)
