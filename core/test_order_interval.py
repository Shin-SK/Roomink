"""予約間隔は登録順・入口によらず同じ結果になることを検証する。"""
from datetime import date, datetime, time, timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient, APIRequestFactory

from core.models import Cast, Course, Customer, Order, Room, ShiftAssignment, Store, UserProfile
from core.services.order_availability import build_available_order_slots, cast_has_order_conflict
from core.serializers import OrderCreateSerializer, OrderUpdateSerializer


TOKYO = ZoneInfo("Asia/Tokyo")


@override_settings(SMS_DUMMY_MODE=True)
class OrderIntervalTest(TestCase):
    def setUp(self):
        self.day = date(2030, 1, 15)
        self.store = Store.objects.create(name="間隔QA", timezone="Asia/Tokyo")
        self.cast = Cast.objects.create(store=self.store, name="担当", interval_minutes=15)
        self.room = Room.objects.create(store=self.store, name="QA")
        self.course = Course.objects.create(store=self.store, name="90分", duration=90, price=10000)
        self.customer = Customer.objects.create(store=self.store, phone="09011112222", display_name="QA")
        ShiftAssignment.objects.create(store=self.store, cast=self.cast, room=self.room,
                                       date=self.day, start_time=time(12), end_time=time(2), end_day_offset=1)
        user = get_user_model().objects.create_user("interval_manager")
        UserProfile.objects.create(user=user, store=self.store, role=UserProfile.Role.MANAGER)
        self.client = APIClient()
        self.client.force_authenticate(user)

    def at(self, hour, minute=0):
        return datetime(2030, 1, 15, tzinfo=TOKYO) + timedelta(hours=hour, minutes=minute)

    def order(self, start, end, **kwargs):
        return Order.objects.create(store=self.store, cast=self.cast, room=self.room,
                                    customer=self.customer, course=self.course,
                                    course_name=self.course.name, course_price=10000,
                                    start=start, end=end, status=kwargs.pop("status", Order.Status.CONFIRMED),
                                    **kwargs)

    def test_gap_boundaries_have_identical_results_in_both_registration_orders(self):
        # 期待値は実装の式から作らず、要件の「15分以上」を表に固定する。
        for interval, cases in [(15, [(-1, True), (0, True), (10, True), (14, True), (15, False), (16, False)]),
                                (0, [(-1, True), (0, False), (1, False)]),
                                (30, [(29, True), (30, False), (31, False)])]:
            self.cast.interval_minutes = interval
            self.cast.save(update_fields=["interval_minutes"])
            for gap, expected in cases:
                early = (self.at(18), self.at(19, 30))
                late = (early[1] + timedelta(minutes=gap), early[1] + timedelta(minutes=gap + 90))
                for first, second in [(early, late), (late, early)]:
                    with self.subTest(interval=interval, gap=gap, first=first):
                        existing = self.order(*first)
                        self.assertEqual(cast_has_order_conflict(self.cast, *second), expected)
                        existing.delete()

    def test_slot_list_and_save_check_agree_for_every_minute_around_existing_order(self):
        self.order(self.at(19, 30), self.at(21))
        slots = build_available_order_slots(self.store, self.cast, self.day, slot_minutes=1, duration_minutes=90)
        starts = {datetime.fromisoformat(slot["start_at"]) for slot in slots}
        for minute in range(17 * 60, 22 * 60):
            start = self.at(0, minute)
            with self.subTest(minute=minute):
                # 90分施術の終了後15分を確保できる17:45まで、または21:15以降。
                expected = minute <= 17 * 60 + 45 or minute >= 21 * 60 + 15
                self.assertEqual(start in starts, expected)
                self.assertEqual(not cast_has_order_conflict(self.cast, start, start + timedelta(minutes=90)), expected)

    def test_order_just_after_shift_end_still_blocks_earlier_slot_interval(self):
        shift = ShiftAssignment.objects.get(cast=self.cast)
        shift.end_time, shift.end_day_offset = time(19, 30), 0
        shift.save()
        self.order(self.at(19, 40), self.at(21, 10))
        slots = build_available_order_slots(self.store, self.cast, self.day, slot_minutes=5, duration_minutes=90)
        starts = {slot["start"] for slot in slots}
        self.assertIn("17:55", starts)  # 終了19:25 + 15分 = 先約19:40
        self.assertNotIn("18:00", starts)

    def test_cross_midnight_boundary_in_both_directions(self):
        early = (self.at(22, 30), self.at(24))
        for gap, expected in [(14, True), (15, False)]:
            late = (self.at(24, gap), self.at(25, gap))
            for first, second in [(early, late), (late, early)]:
                with self.subTest(gap=gap, first=first):
                    existing = self.order(*first)
                    self.assertEqual(cast_has_order_conflict(self.cast, *second), expected)
                    existing.delete()

    def test_active_statuses_block_but_cancelled_and_done_do_not(self):
        for status in [*Order.ACTIVE_STATUSES, Order.Status.CANCELLED, Order.Status.DONE]:
            with self.subTest(status=status):
                existing = self.order(self.at(19, 30), self.at(21), status=status)
                self.assertEqual(cast_has_order_conflict(self.cast, self.at(18), self.at(19, 30)),
                                 status in Order.ACTIVE_STATUSES)
                existing.delete()

    def test_other_cast_and_store_do_not_block_and_self_can_be_excluded(self):
        existing = self.order(self.at(19, 30), self.at(21))
        self.assertFalse(cast_has_order_conflict(self.cast, existing.start, existing.end, exclude_order_id=existing.pk))
        for store in [self.store, Store.objects.create(name="別店舗")]:
            other = Cast.objects.create(store=store, name="別担当", interval_minutes=15)
            self.assertFalse(cast_has_order_conflict(other, self.at(18), self.at(19, 30)))

    def test_operator_create_rejects_before_existing_order_and_accepts_exact_gap(self):
        self.order(self.at(19, 30), self.at(21))
        payload = {"customer": self.customer.pk, "cast": self.cast.pk, "course": self.course.pk}
        for start, expected in [(self.at(18), 400), (self.at(17, 45), 201)]:
            with self.subTest(start=start):
                response = self.client.post("/api/orders/", {**payload, "start": start.isoformat()}, format="json")
                self.assertEqual(response.status_code, expected, response.data)
        self.assertEqual(Order.objects.count(), 2)

    def test_operator_edit_rejects_interval_shortage_without_changing_order(self):
        self.order(self.at(19, 30), self.at(21))
        earlier = self.order(self.at(16), self.at(17, 30))
        response = self.client.patch(f"/api/orders/{earlier.pk}/", {
            "start": self.at(18).isoformat(), "end": self.at(19, 30).isoformat(),
        }, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        earlier.refresh_from_db()
        self.assertEqual(earlier.start, self.at(16))
        response = self.client.patch(f"/api/orders/{earlier.pk}/", {
            "start": self.at(17, 45).isoformat(), "end": self.at(19, 15).isoformat(),
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)

    def test_customer_booking_cannot_bypass_interval(self):
        self.order(self.at(19, 30), self.at(21))
        user = get_user_model().objects.create_user("interval_customer")
        self.customer.user = user
        self.customer.save(update_fields=["user"])
        self.client.force_authenticate(user)
        response = self.client.post("/api/cu/bookings/", {
            "cast": self.cast.pk, "course": self.course.pk, "start": self.at(18).isoformat(),
        }, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(Order.objects.count(), 1)

    def test_staff_can_book_valid_gap_but_cast_other_store_and_anonymous_cannot(self):
        self.order(self.at(19, 30), self.at(21))
        for name, store, role, expected in [
            ("staff", self.store, UserProfile.Role.STAFF, 201),
            ("cast", self.store, UserProfile.Role.CAST, 403),
            ("outsider", Store.objects.create(name="他店"), UserProfile.Role.MANAGER, 400),
        ]:
            with self.subTest(role=name):
                user = get_user_model().objects.create_user(name)
                UserProfile.objects.create(user=user, store=store, role=role)
                self.client.force_authenticate(user)
                response = self.client.post("/api/orders/", {
                    "customer": self.customer.pk, "cast": self.cast.pk, "course": self.course.pk,
                    "start": self.at(17, 45).isoformat(),
                }, format="json")
                self.assertEqual(response.status_code, expected, response.data)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post("/api/orders/", {}, format="json").status_code, 403)
        self.assertEqual(Order.objects.count(), 2)

    def test_extension_cannot_consume_interval_before_next_booking(self):
        earlier = self.order(self.at(18), self.at(19, 30))
        self.order(self.at(20), self.at(21, 30))
        for duration, expected in [(30, 400), (15, 200)]:
            with self.subTest(duration=duration):
                response = self.client.post(f"/api/orders/{earlier.pk}/apply_extension/", {
                    "extension_duration": duration, "extension_price": 1000,
                }, format="json")
                self.assertEqual(response.status_code, expected, response.data)
        earlier.refresh_from_db()
        self.assertEqual(earlier.end, self.at(19, 45))

    def test_save_rechecks_a_later_booking_added_after_create_or_edit_validation(self):
        request = APIRequestFactory().post("/api/orders/")
        request.user = self.client.handler._force_user
        for edit in [False, True]:
            with self.subTest(edit=edit):
                earlier = self.order(self.at(16), self.at(17, 30)) if edit else None
                payload = {"customer": self.customer.pk, "cast": self.cast.pk, "course": self.course.pk,
                           "start": self.at(18).isoformat(), "end": self.at(19, 30).isoformat()}
                serializer = (OrderUpdateSerializer(earlier, data=payload, partial=True, context={"request": request})
                              if edit else OrderCreateSerializer(data=payload, context={"request": request}))
                self.assertTrue(serializer.is_valid(), serializer.errors)
                self.order(self.at(19, 30), self.at(21))
                with self.assertRaises(ValidationError):
                    serializer.save()
                self.assertEqual(Order.objects.count(), 2 if edit else 1)
                if edit:
                    earlier.refresh_from_db()
                    self.assertEqual(earlier.start, self.at(16))
                Order.objects.all().delete()


@override_settings(SMS_DUMMY_MODE=True)
@skipUnlessDBFeature("has_select_for_update")
class OrderIntervalConcurrencyTest(TransactionTestCase):
    def setUp(self):
        # 古いschemaの移行試験が先に走っても、現行schemaの実ロックで検証する。
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        OrderIntervalTest.setUp(self)

    at = OrderIntervalTest.at

    def test_simultaneous_before_and_after_bookings_respect_gap(self):
        actor = self.client.handler._force_user
        for gap, expected in [(0, [201, 400]), (15, [201, 201])]:
            barrier = Barrier(2)

            def book(start):
                close_old_connections()
                try:
                    client = APIClient()
                    client.force_authenticate(actor)
                    barrier.wait(timeout=10)
                    return client.post("/api/orders/", {
                        "customer": self.customer.pk, "cast": self.cast.pk, "course": self.course.pk,
                        "start": start.isoformat(),
                    }, format="json").status_code
                finally:
                    close_old_connections()

            with self.subTest(gap=gap), ThreadPoolExecutor(max_workers=2) as pool:
                jobs = [pool.submit(book, start) for start in [self.at(18), self.at(19, 30 + gap)]]
                self.assertEqual(sorted(job.result(timeout=30) for job in jobs), expected)
                self.assertEqual(Order.objects.count(), expected.count(201))
            Order.objects.all().delete()
