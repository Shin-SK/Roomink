from datetime import date, datetime, time, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import (
    Cast,
    Course,
    Customer,
    Extension,
    Order,
    Room,
    ShiftAssignment,
    Store,
    UserProfile,
)


User = get_user_model()
TOKYO = ZoneInfo("Asia/Tokyo")


class OrderExtensionDurationTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="延長テスト店舗", timezone="Asia/Tokyo")
        self.cast = Cast.objects.create(store=self.store, name="延長キャスト")
        self.room = Room.objects.create(store=self.store, name="101")
        self.customer_user = User.objects.create_user("extension_customer")
        self.customer = Customer.objects.create(
            store=self.store,
            user=self.customer_user,
            phone="09011112222",
            display_name="延長顧客",
        )
        self.course = Course.objects.create(
            store=self.store,
            name="60分コース",
            duration=60,
            price=10000,
        )
        self.extension = Extension.objects.create(
            store=self.store,
            name="30分延長",
            duration=30,
            price=5000,
        )
        self.business_date = date(2026, 8, 9)
        ShiftAssignment.objects.create(
            store=self.store,
            date=self.business_date,
            cast=self.cast,
            room=self.room,
            start_time=time(10, 0),
            end_time=time(18, 0),
        )
        self.manager = User.objects.create_user("extension_manager")
        UserProfile.objects.create(
            user=self.manager,
            store=self.store,
            role=UserProfile.Role.MANAGER,
        )
        self.staff = User.objects.create_user("extension_staff")
        UserProfile.objects.create(
            user=self.staff,
            store=self.store,
            role=UserProfile.Role.STAFF,
        )
        self.cast_user = User.objects.create_user("extension_cast")
        UserProfile.objects.create(
            user=self.cast_user,
            store=self.store,
            role=UserProfile.Role.CAST,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.manager)
        self.staff_client = APIClient()
        self.staff_client.force_authenticate(self.staff)
        self.cast_client = APIClient()
        self.cast_client.force_authenticate(self.cast_user)

    def create_order(self, start_hour=12, end_hour=13):
        start = datetime(2026, 8, 9, start_hour, 0, tzinfo=TOKYO)
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
            end=datetime(2026, 8, 9, end_hour, 0, tzinfo=TOKYO),
            status=Order.Status.CONFIRMED,
        )

    def test_create_with_extension_updates_end_and_price_snapshots(self):
        start = datetime(2026, 8, 9, 12, 0, tzinfo=TOKYO)

        response = self.client.post(
            "/api/orders/",
            {
                "customer": self.customer.id,
                "cast": self.cast.id,
                "course": self.course.id,
                "extension": self.extension.id,
                "start": start.isoformat(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        order = Order.objects.get(pk=response.data["id"])
        self.assertEqual(order.extension, self.extension)
        self.assertEqual(order.extension_name, "30分延長")
        self.assertEqual(order.extension_duration, 30)
        self.assertEqual(order.extension_price, 5000)
        self.assertEqual(order.end.astimezone(TOKYO), start + timedelta(minutes=90))
        self.assertEqual(order.total_price, 15000)

    def test_apply_and_remove_extension_recalculates_end_and_total(self):
        order = self.create_order()

        applied = self.client.post(
            f"/api/orders/{order.id}/apply_extension/",
            {"extension_id": self.extension.id},
            format="json",
        )

        self.assertEqual(applied.status_code, 200, applied.data)
        order.refresh_from_db()
        self.assertEqual(order.end.astimezone(TOKYO).hour, 13)
        self.assertEqual(order.end.astimezone(TOKYO).minute, 30)
        self.assertEqual(order.total_price, 15000)

        removed = self.client.post(
            f"/api/orders/{order.id}/apply_extension/",
            {"extension_id": None},
            format="json",
        )

        self.assertEqual(removed.status_code, 200, removed.data)
        order.refresh_from_db()
        self.assertIsNone(order.extension)
        self.assertEqual(order.extension_duration, 0)
        self.assertEqual(order.end.astimezone(TOKYO).hour, 13)
        self.assertEqual(order.end.astimezone(TOKYO).minute, 0)
        self.assertEqual(order.total_price, 10000)

    def test_apply_extension_rejects_shift_overrun_without_changes(self):
        order = self.create_order(start_hour=17, end_hour=18)
        original_end = order.end

        response = self.client.post(
            f"/api/orders/{order.id}/apply_extension/",
            {"extension_id": self.extension.id},
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.data)
        order.refresh_from_db()
        self.assertIsNone(order.extension)
        self.assertEqual(order.end, original_end)
        self.assertEqual(order.total_price, 10000)

    def test_create_with_direct_extension_duration_and_price(self):
        start = datetime(2026, 8, 9, 12, 0, tzinfo=TOKYO)

        response = self.client.post(
            "/api/orders/",
            {
                "customer": self.customer.id,
                "cast": self.cast.id,
                "course": self.course.id,
                "extension_duration": 15,
                "extension_price": 3000,
                "start": start.isoformat(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        order = Order.objects.get(pk=response.data["id"])
        self.assertIsNone(order.extension)
        self.assertEqual(order.extension_name, "15分延長")
        self.assertEqual(order.extension_duration, 15)
        self.assertEqual(order.extension_price, 3000)
        self.assertEqual(order.end.astimezone(TOKYO), start + timedelta(minutes=75))
        self.assertEqual(order.total_price, 13000)

    def test_customer_reservation_returns_extension_duration(self):
        order = self.create_order()
        order.extension_name = "15分延長"
        order.extension_duration = 15
        order.extension_price = 3000
        order.end += timedelta(minutes=15)
        order.total_price = 13000
        order.save(update_fields=[
            "extension_name", "extension_duration", "extension_price", "end", "total_price",
        ])
        customer_client = APIClient()
        customer_client.force_authenticate(self.customer_user)

        response = customer_client.get(f"/api/cu/reservations/{order.id}/")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["extension_name"], "15分延長")
        self.assertEqual(response.data["extension_duration"], 15)
        self.assertEqual(response.data["extension_price"], 3000)

    def test_create_can_override_extension_template_values(self):
        start = datetime(2026, 8, 9, 12, 0, tzinfo=TOKYO)

        response = self.client.post(
            "/api/orders/",
            {
                "customer": self.customer.id,
                "cast": self.cast.id,
                "course": self.course.id,
                "extension": self.extension.id,
                "extension_duration": 15,
                "extension_price": 2500,
                "start": start.isoformat(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        order = Order.objects.get(pk=response.data["id"])
        self.assertEqual(order.extension, self.extension)
        self.assertEqual(order.extension_name, "15分延長")
        self.assertEqual(order.extension_duration, 15)
        self.assertEqual(order.extension_price, 2500)
        self.assertEqual(order.end.astimezone(TOKYO), start + timedelta(minutes=75))
        self.assertEqual(order.total_price, 12500)

    def test_apply_and_remove_direct_extension(self):
        order = self.create_order()

        applied = self.client.post(
            f"/api/orders/{order.id}/apply_extension/",
            {
                "extension_id": None,
                "extension_duration": 15,
                "extension_price": 3000,
            },
            format="json",
        )

        self.assertEqual(applied.status_code, 200, applied.data)
        order.refresh_from_db()
        self.assertIsNone(order.extension)
        self.assertEqual(order.extension_name, "15分延長")
        self.assertEqual(order.extension_duration, 15)
        self.assertEqual(order.extension_price, 3000)
        self.assertEqual(order.end.astimezone(TOKYO).time(), time(13, 15))
        self.assertEqual(order.total_price, 13000)

        removed = self.client.post(
            f"/api/orders/{order.id}/apply_extension/",
            {
                "extension_id": None,
                "extension_duration": 0,
                "extension_price": 0,
            },
            format="json",
        )

        self.assertEqual(removed.status_code, 200, removed.data)
        order.refresh_from_db()
        self.assertEqual(order.extension_name, "")
        self.assertEqual(order.extension_duration, 0)
        self.assertEqual(order.extension_price, 0)
        self.assertEqual(order.end.astimezone(TOKYO).time(), time(13, 0))
        self.assertEqual(order.total_price, 10000)

    def test_extension_price_without_duration_is_rejected_without_changes(self):
        order = self.create_order()
        original_end = order.end

        response = self.client.post(
            f"/api/orders/{order.id}/apply_extension/",
            {
                "extension_id": None,
                "extension_duration": 0,
                "extension_price": 3000,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.data)
        order.refresh_from_db()
        self.assertEqual(order.end, original_end)
        self.assertEqual(order.total_price, 10000)

    def test_create_rejects_non_five_minute_or_over_180_minute_extension(self):
        start = datetime(2026, 8, 9, 14, 0, tzinfo=TOKYO)

        for duration in (16, 185):
            with self.subTest(duration=duration):
                response = self.client.post(
                    "/api/orders/",
                    {
                        "customer": self.customer.id,
                        "cast": self.cast.id,
                        "course": self.course.id,
                        "extension_duration": duration,
                        "extension_price": 3000,
                        "start": start.isoformat(),
                    },
                    format="json",
                )
                self.assertEqual(response.status_code, 400, response.data)

        self.assertEqual(Order.objects.count(), 0)

    def test_apply_rejects_invalid_duration_without_changes(self):
        order = self.create_order()
        original_end = order.end

        for duration in (16, 185):
            with self.subTest(duration=duration):
                response = self.client.post(
                    f"/api/orders/{order.id}/apply_extension/",
                    {
                        "extension_id": None,
                        "extension_duration": duration,
                        "extension_price": 3000,
                    },
                    format="json",
                )
                self.assertEqual(response.status_code, 400, response.data)

        order.refresh_from_db()
        self.assertEqual(order.end, original_end)
        self.assertEqual(order.extension_duration, 0)
        self.assertEqual(order.total_price, 10000)

    def test_staff_can_apply_extension_during_pending_finalize(self):
        order = self.create_order()
        order.status = Order.Status.PENDING_FINALIZE
        order.save(update_fields=["status"])

        reference_at = datetime(2026, 8, 9, 15, 0, tzinfo=TOKYO)
        with patch("core.permissions.timezone.now", return_value=reference_at):
            response = self.staff_client.post(
                f"/api/orders/{order.id}/apply_extension/",
                {
                    "extension_id": None,
                    "extension_duration": 15,
                    "extension_price": 3000,
                },
                format="json",
            )

        self.assertEqual(response.status_code, 200, response.data)
        order.refresh_from_db()
        self.assertEqual(order.extension_duration, 15)

    def test_cast_cannot_apply_extension(self):
        order = self.create_order()

        response = self.cast_client.post(
            f"/api/orders/{order.id}/apply_extension/",
            {
                "extension_id": None,
                "extension_duration": 15,
                "extension_price": 3000,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 403, response.data)
        order.refresh_from_db()
        self.assertEqual(order.extension_duration, 0)

    def test_done_order_cannot_be_extended(self):
        order = self.create_order()
        order.status = Order.Status.DONE
        order.save(update_fields=["status"])

        response = self.client.post(
            f"/api/orders/{order.id}/apply_extension/",
            {
                "extension_id": None,
                "extension_duration": 15,
                "extension_price": 3000,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 403, response.data)
        order.refresh_from_db()
        self.assertEqual(order.extension_duration, 0)

    def test_extension_master_rejects_invalid_duration(self):
        original_count = Extension.objects.count()

        for duration in (16, 185):
            with self.subTest(duration=duration):
                response = self.client.post(
                    "/api/extensions/",
                    {
                        "name": f"{duration}分延長",
                        "duration": duration,
                        "price": 3000,
                        "is_active": True,
                    },
                    format="json",
                )
                self.assertEqual(response.status_code, 400, response.data)

        self.assertEqual(Extension.objects.count(), original_count)

    def test_apply_extension_rejects_order_conflict_without_changes(self):
        order = self.create_order()
        conflict_start = datetime(2026, 8, 9, 13, 15, tzinfo=TOKYO)
        Order.objects.create(
            store=self.store,
            cast=self.cast,
            room=self.room,
            customer=self.customer,
            course=self.course,
            course_name=self.course.name,
            course_price=self.course.price,
            total_price=self.course.price,
            start=conflict_start,
            end=conflict_start + timedelta(hours=1),
            status=Order.Status.CONFIRMED,
        )
        original_end = order.end

        response = self.client.post(
            f"/api/orders/{order.id}/apply_extension/",
            {"extension_id": self.extension.id},
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.data)
        order.refresh_from_db()
        self.assertIsNone(order.extension)
        self.assertEqual(order.end, original_end)
        self.assertEqual(order.total_price, 10000)

    def test_create_rejects_inactive_or_other_store_extension(self):
        self.extension.is_active = False
        self.extension.save(update_fields=["is_active"])
        other_store = Store.objects.create(name="別店舗")
        other_extension = Extension.objects.create(
            store=other_store,
            name="別店舗延長",
            duration=30,
            price=5000,
        )
        start = datetime(2026, 8, 9, 14, 0, tzinfo=TOKYO)

        for extension_id in (self.extension.id, other_extension.id):
            with self.subTest(extension_id=extension_id):
                response = self.client.post(
                    "/api/orders/",
                    {
                        "customer": self.customer.id,
                        "cast": self.cast.id,
                        "course": self.course.id,
                        "extension": extension_id,
                        "start": start.isoformat(),
                    },
                    format="json",
                )
                self.assertEqual(response.status_code, 400, response.data)

        self.assertEqual(Order.objects.count(), 0)

    def test_apply_rejects_inactive_or_other_store_extension_without_changes(self):
        order = self.create_order()
        self.extension.is_active = False
        self.extension.save(update_fields=["is_active"])
        other_store = Store.objects.create(name="別店舗")
        other_extension = Extension.objects.create(
            store=other_store,
            name="別店舗延長",
            duration=30,
            price=5000,
        )
        original_end = order.end

        for extension_id in (self.extension.id, other_extension.id):
            with self.subTest(extension_id=extension_id):
                response = self.client.post(
                    f"/api/orders/{order.id}/apply_extension/",
                    {"extension_id": extension_id},
                    format="json",
                )
                self.assertEqual(response.status_code, 400, response.data)

        order.refresh_from_db()
        self.assertIsNone(order.extension)
        self.assertEqual(order.end, original_end)
        self.assertEqual(order.total_price, 10000)
