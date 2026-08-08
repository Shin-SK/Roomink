from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

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


class OrderBusinessDateTimeTest(TestCase):
    def setUp(self):
        self.business_date = date(2026, 7, 31)
        self.store = Store.objects.create(name="深夜営業店舗", timezone="Asia/Tokyo")
        self.cast = Cast.objects.create(
            store=self.store,
            name="深夜キャスト",
            interval_minutes=15,
        )
        self.room = Room.objects.create(store=self.store, name="101")
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
            end_time=time(5, 0),
            end_day_offset=1,
        )

        self.manager = User.objects.create_user("order_manager", password="pass")
        UserProfile.objects.create(
            user=self.manager,
            store=self.store,
            role=UserProfile.Role.MANAGER,
        )
        self.manager_client = APIClient()
        self.manager_client.force_authenticate(self.manager)

        self.customer_user = User.objects.create_user("order_customer", password="pass")
        self.customer.user = self.customer_user
        self.customer.save(update_fields=["user"])
        self.customer_client = APIClient()
        self.customer_client.force_authenticate(self.customer_user)

    def order_payload(self, start):
        return {
            "customer": self.customer.id,
            "cast": self.cast.id,
            "course": self.course.id,
            "start": start.isoformat(),
        }

    def test_manager_can_create_order_in_previous_business_days_extended_shift(self):
        start = datetime(2026, 8, 1, 3, 0, tzinfo=TOKYO)

        response = self.manager_client.post(
            "/api/orders/",
            self.order_payload(start),
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        order = Order.objects.get(pk=response.data["id"])
        self.assertEqual(order.room, self.room)
        self.assertEqual(order.start.astimezone(TOKYO), start)
        self.assertEqual(order.end.astimezone(TOKYO), start + timedelta(minutes=60))

    def test_cross_midnight_existing_order_and_interval_blocks_conflicting_order(self):
        existing_start = datetime(2026, 7, 31, 23, 30, tzinfo=TOKYO)
        Order.objects.create(
            store=self.store,
            cast=self.cast,
            room=self.room,
            customer=self.customer,
            course=self.course,
            course_name=self.course.name,
            course_price=self.course.price,
            total_price=self.course.price,
            start=existing_start,
            end=datetime(2026, 8, 1, 0, 30, tzinfo=TOKYO),
            status=Order.Status.CONFIRMED,
        )

        response = self.manager_client.post(
            "/api/orders/",
            self.order_payload(datetime(2026, 8, 1, 0, 30, tzinfo=TOKYO)),
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("インターバル", str(response.data))
        self.assertEqual(Order.objects.count(), 1)

    def test_manager_can_move_existing_order_into_extended_shift(self):
        order = Order.objects.create(
            store=self.store,
            cast=self.cast,
            room=self.room,
            customer=self.customer,
            course=self.course,
            course_name=self.course.name,
            course_price=self.course.price,
            total_price=self.course.price,
            start=datetime(2026, 7, 31, 20, 0, tzinfo=TOKYO),
            end=datetime(2026, 7, 31, 21, 0, tzinfo=TOKYO),
            status=Order.Status.CONFIRMED,
        )

        response = self.manager_client.patch(
            f"/api/orders/{order.id}/",
            {
                "start": "2026-08-01T03:00:00+09:00",
                "end": "2026-08-01T04:00:00+09:00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        order.refresh_from_db()
        self.assertEqual(order.start.astimezone(TOKYO).hour, 3)
        self.assertEqual(order.room, self.room)

    def test_customer_can_book_real_datetime_from_extended_slot(self):
        response = self.customer_client.post(
            "/api/cu/bookings/",
            {
                "cast": self.cast.id,
                "course": self.course.id,
                "start": "2026-08-01T03:00:00+09:00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        order = Order.objects.get(pk=response.data["id"])
        self.assertEqual(order.customer, self.customer)
        self.assertEqual(order.start.astimezone(TOKYO).hour, 3)

    def test_customer_slots_keep_business_day_display_and_real_datetimes(self):
        response = self.customer_client.get(
            f"/api/cu/available-slots/?cast={self.cast.id}&date={self.business_date.isoformat()}"
        )

        self.assertEqual(response.status_code, 200, response.data)
        slots_by_start = {slot["start"]: slot for slot in response.data["slots"]}
        self.assertIn("24:00", slots_by_start)
        self.assertIn("28:30", slots_by_start)
        self.assertEqual(
            slots_by_start["24:00"]["start_at"],
            "2026-08-01T00:00:00+09:00",
        )
        self.assertEqual(slots_by_start["28:30"]["end"], "29:00")

    def test_cross_midnight_order_is_removed_from_customer_slots(self):
        Order.objects.create(
            store=self.store,
            cast=self.cast,
            room=self.room,
            customer=self.customer,
            course=self.course,
            course_name=self.course.name,
            course_price=self.course.price,
            total_price=self.course.price,
            start=datetime(2026, 7, 31, 23, 30, tzinfo=TOKYO),
            end=datetime(2026, 8, 1, 0, 30, tzinfo=TOKYO),
            status=Order.Status.CONFIRMED,
        )

        response = self.customer_client.get(
            f"/api/cu/available-slots/?cast={self.cast.id}&date={self.business_date.isoformat()}"
        )

        self.assertEqual(response.status_code, 200, response.data)
        starts = {slot["start"] for slot in response.data["slots"]}
        self.assertNotIn("23:30", starts)
        self.assertNotIn("24:00", starts)
        self.assertNotIn("24:30", starts)
        self.assertIn("25:00", starts)

    def test_same_day_order_creation_still_works(self):
        start = datetime(2026, 7, 31, 20, 0, tzinfo=TOKYO)

        response = self.manager_client.post(
            "/api/orders/",
            self.order_payload(start),
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
