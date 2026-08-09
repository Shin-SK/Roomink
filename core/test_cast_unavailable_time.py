from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import (
    Cast,
    CastUnavailableTime,
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


class CastUnavailableTimeTest(TestCase):
    def setUp(self):
        self.business_date = date(2026, 8, 12)
        self.store = Store.objects.create(name="予約不可テスト店", timezone="Asia/Tokyo")
        self.cast = Cast.objects.create(store=self.store, name="予約不可キャスト")
        self.room = Room.objects.create(store=self.store, name="101")
        self.customer_user = User.objects.create_user("unavailable_customer")
        self.customer = Customer.objects.create(
            store=self.store,
            user=self.customer_user,
            phone="09012345678",
            display_name="予約不可顧客",
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
            cast=self.cast,
            room=self.room,
            start_time=time(10, 0),
            end_time=time(18, 0),
        )

        self.manager = self.create_operator("unavailable_manager", UserProfile.Role.MANAGER)
        self.staff = self.create_operator("unavailable_staff", UserProfile.Role.STAFF)
        self.cast_user = self.create_operator("unavailable_cast_user", UserProfile.Role.CAST)
        self.manager_client = self.authenticated_client(self.manager)
        self.staff_client = self.authenticated_client(self.staff)
        self.cast_client = self.authenticated_client(self.cast_user)

    def create_operator(self, username, role):
        user = User.objects.create_user(username)
        UserProfile.objects.create(user=user, store=self.store, role=role)
        return user

    def authenticated_client(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def at(self, hour, minute=0):
        return datetime(2026, 8, 12, hour, minute, tzinfo=TOKYO)

    def payload(self, start_hour=13, end_hour=14, unavailable_type="BREAK"):
        return {
            "cast": self.cast.id,
            "start_at": self.at(start_hour).isoformat(),
            "end_at": self.at(end_hour).isoformat(),
            "type": unavailable_type,
            "memo": "運営登録",
        }

    def create_order(self, start_hour=12, end_hour=13, status=Order.Status.CONFIRMED):
        return Order.objects.create(
            store=self.store,
            cast=self.cast,
            room=self.room,
            customer=self.customer,
            course=self.course,
            course_name=self.course.name,
            course_price=self.course.price,
            total_price=self.course.price,
            start=self.at(start_hour),
            end=self.at(end_hour),
            status=status,
        )

    def test_manager_and_staff_can_create_with_audit_users(self):
        manager_response = self.manager_client.post(
            "/api/cast-unavailable-times/",
            self.payload(13, 14, "BREAK"),
            format="json",
        )
        staff_response = self.staff_client.post(
            "/api/cast-unavailable-times/",
            self.payload(15, 16, "OUT"),
            format="json",
        )

        self.assertEqual(manager_response.status_code, 201, manager_response.data)
        self.assertEqual(staff_response.status_code, 201, staff_response.data)
        manager_block = CastUnavailableTime.objects.get(pk=manager_response.data["id"])
        staff_block = CastUnavailableTime.objects.get(pk=staff_response.data["id"])
        self.assertEqual(manager_block.created_by, self.manager)
        self.assertEqual(manager_block.updated_by, self.manager)
        self.assertEqual(staff_block.created_by, self.staff)
        self.assertEqual(staff_response.data["type_display"], "中抜け")

        updated = self.staff_client.patch(
            f"/api/cast-unavailable-times/{manager_block.id}/",
            {
                "business_date": self.business_date.isoformat(),
                "start_time_extended": "14:00",
                "end_time_extended": "15:00",
                "type": "LATE",
                "memo": "遅刻へ変更",
            },
            format="json",
        )
        self.assertEqual(updated.status_code, 200, updated.data)
        manager_block.refresh_from_db()
        self.assertEqual(manager_block.created_by, self.manager)
        self.assertEqual(manager_block.updated_by, self.staff)
        self.assertEqual(updated.data["start_time_extended"], "14:00")

    def test_cast_cannot_create_or_update(self):
        block = CastUnavailableTime.objects.create(
            store=self.store,
            cast=self.cast,
            start_at=self.at(13),
            end_at=self.at(14),
            type=CastUnavailableTime.Type.BREAK,
            created_by=self.manager,
            updated_by=self.manager,
        )

        created = self.cast_client.post(
            "/api/cast-unavailable-times/",
            self.payload(15, 16),
            format="json",
        )
        updated = self.cast_client.patch(
            f"/api/cast-unavailable-times/{block.id}/",
            {"memo": "変更"},
            format="json",
        )

        self.assertEqual(created.status_code, 403, created.data)
        self.assertEqual(updated.status_code, 403, updated.data)
        block.refresh_from_db()
        self.assertEqual(block.memo, "")

    def test_outside_shift_and_existing_order_overlap_are_rejected(self):
        outside = self.manager_client.post(
            "/api/cast-unavailable-times/",
            self.payload(9, 10),
            format="json",
        )
        self.create_order(13, 14)
        overlap = self.manager_client.post(
            "/api/cast-unavailable-times/",
            self.payload(13, 14),
            format="json",
        )

        self.assertEqual(outside.status_code, 400, outside.data)
        self.assertEqual(overlap.status_code, 400, overlap.data)
        self.assertEqual(CastUnavailableTime.objects.count(), 0)

    def test_cancelled_order_does_not_block_registration(self):
        self.create_order(13, 14, status=Order.Status.CANCELLED)

        response = self.manager_client.post(
            "/api/cast-unavailable-times/",
            self.payload(13, 14),
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)

    def test_overlapping_unavailable_time_is_rejected(self):
        CastUnavailableTime.objects.create(
            store=self.store,
            cast=self.cast,
            start_at=self.at(13),
            end_at=self.at(14),
            type=CastUnavailableTime.Type.BREAK,
        )

        response = self.manager_client.post(
            "/api/cast-unavailable-times/",
            self.payload(13, 15),
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(CastUnavailableTime.objects.count(), 1)

    def test_other_store_records_are_hidden_and_cast_is_rejected(self):
        other_store = Store.objects.create(name="別店舗")
        other_cast = Cast.objects.create(store=other_store, name="別店舗キャスト")
        CastUnavailableTime.objects.create(
            store=other_store,
            cast=other_cast,
            start_at=self.at(13),
            end_at=self.at(14),
            type=CastUnavailableTime.Type.BREAK,
        )

        listed = self.manager_client.get("/api/cast-unavailable-times/")
        created = self.manager_client.post(
            "/api/cast-unavailable-times/",
            {**self.payload(15, 16), "cast": other_cast.id},
            format="json",
        )

        self.assertEqual(listed.status_code, 200, listed.data)
        self.assertEqual(listed.data["count"], 0)
        self.assertEqual(created.status_code, 400, created.data)

    def test_order_create_and_update_reject_unavailable_time(self):
        CastUnavailableTime.objects.create(
            store=self.store,
            cast=self.cast,
            start_at=self.at(13),
            end_at=self.at(14),
            type=CastUnavailableTime.Type.BREAK,
        )

        created = self.manager_client.post(
            "/api/orders/",
            {
                "customer": self.customer.id,
                "cast": self.cast.id,
                "course": self.course.id,
                "start": self.at(13).isoformat(),
            },
            format="json",
        )
        order = self.create_order(11, 12)
        updated = self.manager_client.patch(
            f"/api/orders/{order.id}/",
            {"start": self.at(13).isoformat(), "end": self.at(14).isoformat()},
            format="json",
        )

        self.assertEqual(created.status_code, 400, created.data)
        self.assertEqual(updated.status_code, 400, updated.data)
        order.refresh_from_db()
        self.assertEqual(order.start, self.at(11))

    def test_extension_rejects_unavailable_time_without_changes(self):
        order = self.create_order(12, 13)
        CastUnavailableTime.objects.create(
            store=self.store,
            cast=self.cast,
            start_at=self.at(13),
            end_at=self.at(14),
            type=CastUnavailableTime.Type.BREAK,
        )

        response = self.manager_client.post(
            f"/api/orders/{order.id}/apply_extension/",
            {"extension_id": None, "extension_duration": 30, "extension_price": 3000},
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.data)
        order.refresh_from_db()
        self.assertEqual(order.end, self.at(13))
        self.assertEqual(order.extension_duration, 0)

    def test_customer_slots_and_schedule_exclude_and_show_unavailable_time(self):
        block = CastUnavailableTime.objects.create(
            store=self.store,
            cast=self.cast,
            start_at=self.at(12, 30),
            end_at=self.at(13, 30),
            type=CastUnavailableTime.Type.BREAK,
            memo="昼休憩",
        )
        customer_client = self.authenticated_client(self.customer_user)

        slots = customer_client.get(
            f"/api/cu/available-slots/?cast={self.cast.id}&date={self.business_date.isoformat()}"
        )
        schedule = self.manager_client.get(
            f"/api/op/schedule/?date={self.business_date.isoformat()}"
        )

        self.assertEqual(slots.status_code, 200, slots.data)
        starts = {item["start"] for item in slots.data["slots"]}
        self.assertIn("12:00", starts)
        self.assertNotIn("12:30", starts)
        self.assertNotIn("13:00", starts)
        self.assertEqual(schedule.status_code, 200, schedule.data)
        self.assertEqual(len(schedule.data["unavailable_times"]), 1)
        self.assertEqual(schedule.data["unavailable_times"][0]["id"], block.id)
        self.assertEqual(schedule.data["unavailable_times"][0]["start_time_extended"], "12:30")

    def test_next_day_extended_interval_is_supported(self):
        late_date = date(2026, 8, 13)
        ShiftAssignment.objects.create(
            store=self.store,
            date=late_date,
            cast=self.cast,
            room=self.room,
            start_time=time(18, 0),
            end_time=time(5, 0),
            end_day_offset=1,
        )
        response = self.manager_client.post(
            "/api/cast-unavailable-times/",
            {
                "cast": self.cast.id,
                "business_date": late_date.isoformat(),
                "start_time_extended": "25:00",
                "end_time_extended": "26:00",
                "type": "OTHER",
                "memo": "深夜対応",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["business_date"], late_date.isoformat())
        self.assertEqual(response.data["start_time_extended"], "25:00")
        self.assertEqual(response.data["end_time_extended"], "26:00")
