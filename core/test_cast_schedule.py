from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Cast, Course, Customer, Order, Room, ShiftAssignment, Store, UserProfile


User = get_user_model()
TOKYO = ZoneInfo("Asia/Tokyo")


class CastScheduleTest(TestCase):
    def setUp(self):
        self.day = date(2026, 9, 19)
        self.store = Store.objects.create(name="テスト店舗", timezone="Asia/Tokyo")
        self.other_store = Store.objects.create(name="別店舗", timezone="Asia/Tokyo")
        self.room_a = Room.objects.create(
            store=self.store, name="Aルーム", sort_order=1,
            address="東京都新宿区テスト1-2-3", map_url="https://maps.example.com/room-a",
        )
        self.room_b = Room.objects.create(store=self.store, name="Bルーム", sort_order=2)
        Room.objects.create(store=self.other_store, name="秘密の部屋")

        self.user = User.objects.create_user("cast_schedule_owner")
        UserProfile.objects.create(user=self.user, store=self.store, role=UserProfile.Role.CAST)
        self.cast = Cast.objects.create(store=self.store, user=self.user, name="本人")
        self.other_user = User.objects.create_user("cast_schedule_other")
        UserProfile.objects.create(user=self.other_user, store=self.store, role=UserProfile.Role.CAST)
        self.other_cast = Cast.objects.create(
            store=self.store, user=self.other_user, name="他キャスト秘密名",
        )
        self.customer = Customer.objects.create(
            store=self.store, phone="09000000001", display_name="本人の予約者",
        )
        self.course = Course.objects.create(
            store=self.store, name="60分", duration=60, price=10000,
        )
        self.other_customer = Customer.objects.create(
            store=self.store, phone="09000000002", display_name="他人の予約者秘密名",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

        self.own_shift = ShiftAssignment.objects.create(
            store=self.store,
            date=self.day,
            cast=self.cast,
            room=self.room_a,
            start_time=time(11),
            end_time=time(5),
            end_day_offset=1,
        )
        ShiftAssignment.objects.create(
            store=self.store,
            date=self.day,
            cast=self.other_cast,
            room=self.room_b,
            start_time=time(13),
            end_time=time(21),
        )
        ShiftAssignment.objects.create(
            store=self.store,
            date=self.day + timedelta(days=1),
            cast=self.cast,
            room=self.room_b,
            start_time=time(12),
            end_time=time(18),
            is_absent=True,
        )
        self.own_order = self.create_order(
            cast=self.cast,
            room=self.room_a,
            customer=self.customer,
            start=datetime(2026, 9, 20, 3, 0, tzinfo=TOKYO),
            end=datetime(2026, 9, 20, 4, 0, tzinfo=TOKYO),
        )
        self.create_order(
            cast=self.other_cast,
            room=self.room_b,
            customer=self.other_customer,
            start=datetime(2026, 9, 19, 14, 0, tzinfo=TOKYO),
            end=datetime(2026, 9, 19, 15, 0, tzinfo=TOKYO),
        )
        self.create_order(
            cast=self.cast,
            room=self.room_a,
            customer=self.customer,
            start=datetime(2026, 9, 19, 18, 0, tzinfo=TOKYO),
            end=datetime(2026, 9, 19, 19, 0, tzinfo=TOKYO),
            status=Order.Status.CANCELLED,
        )

    def create_order(self, *, cast, room, customer, start, end, status=Order.Status.CONFIRMED):
        return Order.objects.create(
            store=self.store,
            cast=cast,
            room=room,
            customer=customer,
            course=self.course,
            course_name="60分",
            course_price=10000,
            total_price=10000,
            start=start,
            end=end,
            status=status,
        )

    def test_weekly_own_shifts_and_daily_orders_include_next_calendar_day(self):
        response = self.client.get("/api/cast/schedule/?date=2026-09-19")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["week_start"], "2026-09-19")
        self.assertEqual(len(response.data["days"]), 7)
        day = next(day for day in response.data["days"] if day["date"] == "2026-09-19")
        self.assertEqual(day["shifts"], [{
            "start": "11:00", "end": "29:00", "room_name": "Aルーム",
            "room_address": "東京都新宿区テスト1-2-3",
            "room_map_url": "https://maps.example.com/room-a",
        }])
        self.assertEqual(day["order_count"], 1)
        self.assertEqual(day["orders"], response.data["orders"])
        self.assertEqual(response.data["orders"], [{
            "id": self.own_order.id,
            "start": "27:00",
            "end": "28:00",
            "room_name": "Aルーム",
            "course_name": "60分",
            "status": "CONFIRMED",
        }])
        next_day = next(day for day in response.data["days"] if day["date"] == "2026-09-20")
        self.assertEqual(next_day["shifts"], [])
        self.assertEqual(next_day["orders"], [])
        self.assertEqual(response.data["rooms"], [
            {"name": "Aルーム", "occupied": [{"start": "11:00", "end": "29:00"}]},
            {"name": "Bルーム", "occupied": [{"start": "13:00", "end": "21:00"}]},
        ])
        self.assertNotIn("他キャスト秘密名", str(response.data))
        self.assertNotIn("他人の予約者秘密名", str(response.data))
        self.assertNotIn("09000000002", str(response.data))
        self.assertNotIn("秘密の部屋", str(response.data))

    def test_selected_day_and_week_change_are_live(self):
        self.own_shift.room = self.room_b
        self.own_shift.save(update_fields=["room"])
        response = self.client.get(
            "/api/cast/schedule/?date=2026-09-20&week_start=2026-09-19",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["selected_date"], "2026-09-20")
        self.assertEqual(response.data["orders"], [])
        self.assertEqual(response.data["rooms"][0]["occupied"], [])
        self.assertEqual(response.data["rooms"][1]["occupied"], [])
        changed_day = next(day for day in response.data["days"] if day["date"] == "2026-09-19")
        self.assertEqual(changed_day["shifts"][0]["room_name"], "Bルーム")

        following_week = self.client.get(
            "/api/cast/schedule/?date=2026-09-27&week_start=2026-09-26",
        )
        self.assertEqual(following_week.status_code, 200, following_week.data)
        self.assertEqual(following_week.data["week_start"], "2026-09-26")
        self.assertTrue(all(not day["shifts"] for day in following_week.data["days"]))

    def test_other_roles_and_invalid_date_are_rejected(self):
        invalid = self.client.get("/api/cast/schedule/?date=not-a-date")
        self.assertEqual(invalid.status_code, 400, invalid.data)
        invalid_window = self.client.get(
            "/api/cast/schedule/?date=2026-09-26&week_start=2026-09-19",
        )
        self.assertEqual(invalid_window.status_code, 400, invalid_window.data)

        manager = User.objects.create_user("cast_schedule_manager")
        UserProfile.objects.create(user=manager, store=self.store, role=UserProfile.Role.MANAGER)
        manager_client = APIClient()
        manager_client.force_authenticate(manager)
        forbidden = manager_client.get("/api/cast/schedule/?date=2026-09-19")
        self.assertEqual(forbidden.status_code, 403, forbidden.data)
