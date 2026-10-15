import csv
import io
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.test import TransactionTestCase
from django.db import connection, close_old_connections
from django.core.files.uploadedfile import SimpleUploadedFile
from core.models import Cast, Discount, Order, ShiftAssignment, ShiftRequest, SmsLog
from core import test_card_payment_sms_flow as card_fixtures
from core import test_shift_request_extended_time as shift_fixtures
from core import test_public_web_booking as public_fixtures
from core.services.booking_restrictions import customer_booking_blocked
from core.views import OpShiftRequestViewSet, _apply_shift_request_approval


@override_settings(FRONTEND_URL="https://roomink.example", RESERVATION_LINK_BASE_URL="https://r.roomink.example", SMS_DUMMY_MODE=True)
class OrderQaFixesTest(TestCase):
    def setUp(self):
        self.f = card_fixtures.CardPaymentSmsFlowTest()
        self.f.setUp()

    def test_discount_invalid_missing_and_inactive_do_not_change_existing_discount(self):
        f = self.f
        order = f.create_order(payment_method="CASH", status="CONFIRMED")
        active = Discount.objects.create(store=f.store, name="QA", value=1000)
        inactive = Discount.objects.create(store=f.store, name="無効", value=2000, is_active=False)
        url = f"/api/orders/{order.pk}/apply_discount/"
        self.assertEqual(f.manager_client.post(url, {"discount_id": active.pk}, format="json").status_code, 200)
        for body in ({}, {"discount_id": "bad"}, {"discount_id": inactive.pk}):
            self.assertEqual(f.manager_client.post(url, body, format="json").status_code, 400)
            order.refresh_from_db()
            self.assertEqual(order.discount_amount, 1000)
        self.assertEqual(f.manager_client.post(url, {"discount_id": None}, format="json").status_code, 200)

    def test_guidance_never_sends_and_separates_customer_and_therapist(self):
        f = self.f
        order = f.create_order(payment_method="CASH", status="CONFIRMED")
        response = f.manager_client.post(f"/api/orders/{order.pk}/manual-guidance/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn(f.room.address, response.data["customer"])
        self.assertIn("https://r.roomink.example/r/", response.data["customer"])
        self.assertNotIn(f.customer.phone, response.data["therapist"])
        self.assertNotIn("https://r.roomink.example/r/", response.data["therapist"])
        self.assertEqual(SmsLog.objects.count(), 0)
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_unpaid_card_guidance_hides_room_and_address(self):
        f = self.f
        order = f.create_order(status="CONFIRMED")
        response = f.manager_client.post(f"/api/orders/{order.pk}/manual-guidance/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn(f.room.address, response.data["customer"])
        self.assertNotIn(f.room.name, response.data["customer"])

    def test_cancelled_guidance_and_foreign_order_are_denied(self):
        f = self.f
        order = f.create_order(status="CANCELLED")
        url = f"/api/orders/{order.pk}/manual-guidance/"
        self.assertEqual(f.manager_client.post(url, {}, format="json").status_code, 400)
        from django.contrib.auth import get_user_model
        from core.models import UserProfile
        user = get_user_model().objects.create_user("qa_foreign_manager")
        UserProfile.objects.create(user=user, store=f.other_store, role="manager")
        foreign_client = f.authenticated_client(user)
        self.assertEqual(foreign_client.post(url, {}, format="json").status_code, 404)

    def test_ng_targets_are_independent_of_online_flag(self):
        f = self.f
        f.customer.flag = "BAN"
        f.customer.ban_type = "CAST_NG"
        f.customer.save()
        f.customer.ng_casts.add(f.cast)
        other = Cast.objects.create(store=f.store, name="別担当")
        self.assertTrue(customer_booking_blocked(f.customer, f.cast.pk, online=True))
        self.assertFalse(customer_booking_blocked(f.customer, other.pk, online=True))
        f.customer.online_booking_ng = True
        self.assertTrue(customer_booking_blocked(f.customer, other.pk, online=True))
        self.assertFalse(customer_booking_blocked(f.customer, other.pk, online=False))

    def test_guidance_denies_cast_and_invalidated_link(self):
        f = self.f
        order = f.create_order(payment_method="CASH", status="CONFIRMED")
        url = f"/api/orders/{order.pk}/manual-guidance/"
        cast_user = f.create_operator("qa_guidance_cast", "cast")
        self.assertEqual(f.authenticated_client(cast_user).post(url, {}, format="json").status_code, 403)
        self.assertEqual(f.manager_client.post(url, {}, format="json").status_code, 200)
        from core.models import OrderGuestAccess
        from django.utils import timezone
        OrderGuestAccess.objects.filter(order=order).update(invalidated_at=timezone.now())
        self.assertEqual(f.manager_client.post(url, {}, format="json").status_code, 400)
        self.assertFalse(SmsLog.objects.exists())


class ShiftQaFixesTest(TestCase):
    def setUp(self):
        self.f = shift_fixtures.ShiftRequestExtendedTimeTest()
        self.f.setUp()
        f = self.f
        self.req = ShiftRequest.objects.create(store=f.store, cast=f.cast, date=f.shift_date, start_time="18:00", end_time="23:00")
        self.row = {"shift_request_id": str(self.req.pk), "cast_id": str(f.cast.pk), "approved_date": "2026/08/10", "approved_start_time": "18:00:00", "approved_end_time": "29:00:00", "approved_room_id": str(f.room.pk)}

    def test_csv_normalizes_and_applies_the_same_values(self):
        f = self.f
        checked = OpShiftRequestViewSet()._validate_import_row(f.store, self.row, 2)
        self.assertTrue(checked["can_apply"], checked)
        response = f.manager_client.post("/api/op/shift-requests/import_apply/", {"rows": [self.row]}, format="json")
        self.assertEqual(response.data["applied_count"], 1, response.data)
        self.assertEqual(ShiftAssignment.objects.get().end_day_offset, 1)

    def test_csv_rejects_bad_time_and_occupied_room_during_preview(self):
        f = self.f
        bad = {**self.row, "approved_start_time": "18:00:garbage"}
        self.assertFalse(OpShiftRequestViewSet()._validate_import_row(f.store, bad, 2)["can_apply"])
        other = Cast.objects.create(store=f.store, name="別担当")
        ShiftAssignment.objects.create(store=f.store, cast=other, room=f.room, date=f.shift_date, start_time="18:00", end_time="23:00")
        self.assertFalse(OpShiftRequestViewSet()._validate_import_row(f.store, self.row, 2)["can_apply"])

    def test_duplicate_csv_headers_are_rejected(self):
        headers = list(self.row) + ["approved_date"]
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(headers)
        writer.writerow(list(self.row.values()) + ["2026-08-11"])
        response = self.f.manager_client.post("/api/op/shift-requests/import_preview/", {"file": SimpleUploadedFile("qa.csv", buffer.getvalue().encode())}, format="multipart")
        self.assertEqual(response.status_code, 400)

    def test_history_failure_rolls_back_shift(self):
        original = ShiftRequest.save
        def fail(obj, *args, **kwargs):
            if obj.pk == self.req.pk and obj.status == "APPROVED":
                raise RuntimeError("injected history failure")
            return original(obj, *args, **kwargs)
        with patch.object(ShiftRequest, "save", fail), self.assertRaises(RuntimeError):
            _apply_shift_request_approval(self.req, self.f.store, self.f.shift_date, "18:00", "23:00", 0, "", self.f.manager, room=self.f.room)
        self.assertEqual(ShiftAssignment.objects.count(), 0)

    def test_csv_batch_detects_overlaps_before_apply(self):
        f = self.f
        other = Cast.objects.create(store=f.store, name="同じルームの別担当")
        other_request = ShiftRequest.objects.create(store=f.store, cast=other, date=f.shift_date, start_time="18:00", end_time="23:00")
        row2 = {**self.row, "shift_request_id": str(other_request.pk), "cast_id": str(other.pk)}
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(self.row))
        writer.writeheader()
        writer.writerows([self.row, row2])
        response = f.manager_client.post("/api/op/shift-requests/import_preview/", {"file": SimpleUploadedFile("qa.csv", buffer.getvalue().encode())}, format="multipart")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["applicable_rows"], 1)
        self.assertIn("CSV内", response.data["rows"][1]["errors"][0])

    def test_stale_approval_cannot_create_second_shift(self):
        f = self.f
        stale = ShiftRequest.objects.get(pk=self.req.pk)
        first = _apply_shift_request_approval(self.req, f.store, f.shift_date, "18:00", "20:00", 0, "", f.manager, room=f.room)
        second = _apply_shift_request_approval(stale, f.store, f.shift_date, "20:00", "23:00", 0, "", f.manager, room=f.room)
        self.assertTrue(first[0])
        self.assertFalse(second[0])
        self.assertEqual(ShiftAssignment.objects.count(), 1)


@override_settings(SMS_DUMMY_MODE=True, FRONTEND_URL="https://roomink.example", RESERVATION_LINK_BASE_URL="https://r.roomink.example")
class PublicNgQaFixesTest(TestCase):
    def setUp(self):
        self.f = public_fixtures.PublicWebBookingTest()
        self.f.setUp()

    def test_individual_ng_does_not_block_other_therapist_end_to_end(self):
        from core.models import Customer
        f = self.f
        customer = Customer.objects.create(store=f.store, phone="09012345678", flag="BAN", ban_type="CAST_NG")
        other = Cast.objects.create(store=f.store, name="NG担当")
        customer.ng_casts.add(other)
        requested = f.request_code()
        self.assertEqual(requested.status_code, 201)
        response = f.client.post("/api/public/booking/confirm/", {"verification_id": requested.data["verification_id"], "code": "123456"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)

    def test_online_ng_creates_no_order(self):
        from core.models import Customer
        f = self.f
        Customer.objects.create(store=f.store, phone="09012345678", online_booking_ng=True)
        requested = f.request_code()
        response = f.client.post("/api/public/booking/confirm/", {"verification_id": requested.data["verification_id"], "code": "123456"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Order.objects.exists())

    def test_room_pending_never_becomes_a_bookable_slot(self):
        f = self.f
        ShiftAssignment.objects.filter(store=f.store).update(room=None)
        response = f.client.get("/api/public/booking/slots/", {"store": f.store.pk, "cast": f.cast.pk, "course": f.course.pk, "date": str(f.business_date)})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["slots"], [])


@skipUnless(connection.vendor == "postgresql", "Row-lock competition requires PostgreSQL")
class ConcurrentShiftQaTest(TransactionTestCase):
    def test_two_approvers_cannot_split_one_request_into_two_shifts(self):
        f = shift_fixtures.ShiftRequestExtendedTimeTest()
        f.setUp()
        req = ShiftRequest.objects.create(store=f.store, cast=f.cast, date=f.shift_date, start_time="18:00", end_time="23:00")
        barrier = Barrier(2)
        def approve(start, end):
            close_old_connections()
            try:
                stale = ShiftRequest.objects.get(pk=req.pk)
                barrier.wait(timeout=10)
                return _apply_shift_request_approval(stale, f.store, f.shift_date, start, end, 0, "", f.manager, room=f.room)[0]
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(approve, "18:00", "20:00")
            second = pool.submit(approve, "20:00", "23:00")
            results = [first.result(timeout=20), second.result(timeout=20)]
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(ShiftAssignment.objects.count(), 1)
