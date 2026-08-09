from datetime import date, datetime, time, timedelta
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
        self.customer = Customer.objects.create(
            store=self.store,
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
        self.client = APIClient()
        self.client.force_authenticate(self.manager)

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
