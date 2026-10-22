from datetime import time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models import Cast, Discount, Order, Room, ShiftAssignment, ShiftRequest, SmsLog, UserProfile
from core.services.sales import get_sales_dashboard, get_sales_dashboard_csv
from core import test_public_web_booking as booking_fixtures


@override_settings(SMS_DUMMY_MODE=True, FRONTEND_URL="https://roomink.example", RESERVATION_LINK_BASE_URL="https://r.roomink.example")
class LineFollowupTest(TestCase):
    payload = booking_fixtures.PublicWebBookingTest.payload
    request_code = booking_fixtures.PublicWebBookingTest.request_code

    def setUp(self):
        booking_fixtures.PublicWebBookingTest.setUp(self)
        self.manager = get_user_model().objects.create_user("followup_manager")
        UserProfile.objects.create(user=self.manager, store=self.store, role=UserProfile.Role.MANAGER)
        self.op = APIClient()
        self.op.force_authenticate(self.manager)

    def accept_web(self, **overrides):
        requested = self.request_code(**overrides)
        self.assertEqual(requested.status_code, 201, requested.data)
        result = self.client.post("/api/public/booking/confirm/", {
            "verification_id": requested.data["verification_id"], "code": "123456",
        }, format="json")
        self.assertEqual(result.status_code, 201, result.data)
        return Order.objects.get(pk=result.data["id"])

    def test_receipt_reserves_slot_without_cast_or_confirmation_notice(self):
        with patch("core.services.line_notify.send_order_confirmation_push_once") as cast_push:
            order = self.accept_web()
            cast_push.assert_not_called()
        self.assertEqual(order.status, Order.Status.REQUESTED)
        receipt = order.sms_logs.get()
        self.assertEqual(receipt.template_type, SmsLog.TemplateType.OTHER)
        self.assertNotIn(str(order.total_price), receipt.body)
        self.assertNotIn(self.room.address, receipt.body)
        slots = self.client.get("/api/public/booking/slots/", {"store": self.store.pk, "cast": self.cast.pk, "course": self.course.pk, "date": self.business_date.isoformat()})
        self.assertEqual(slots.status_code, 200, slots.data)
        self.assertEqual(slots.data["slots"], [])
        notifications = self.op.get("/api/op/notifications/")
        self.assertEqual(notifications.status_code, 200, notifications.data)
        self.assertEqual(notifications.data["notifications"][0]["order_status"], "REQUESTED")

    def test_store_edits_then_confirms_once_and_failed_sms_can_retry_once(self):
        order = self.accept_web()
        discount = Discount.objects.create(store=self.store, name="受付確認割引", value=1000)
        edited = self.op.patch(f"/api/orders/{order.id}/", {"discount": discount.pk}, format="json")
        self.assertEqual(edited.status_code, 200, edited.data)
        with patch("core.views.notify_order_confirmed") as send:
            # Simulate a provider failure, which is stored by the send service.
            def fail(order, **kwargs):
                return SmsLog.objects.create(order=order, store=order.store, to_phone=order.customer.phone, body="failed", template_type=SmsLog.TemplateType.RESERVATION_CONFIRMATION, status=SmsLog.Status.FAILED)
            send.side_effect = fail
            confirmed = self.op.post(f"/api/orders/{order.id}/confirm/")
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        self.assertEqual(confirmed.data["total_price"], 21000)
        again = self.op.post(f"/api/orders/{order.id}/confirm/")
        self.assertEqual(again.status_code, 400)
        retry = self.op.post(f"/api/orders/{order.id}/retry-booking-sms/")
        self.assertEqual(retry.status_code, 200, retry.data)
        self.assertEqual(self.op.post(f"/api/orders/{order.id}/retry-booking-sms/").status_code, 400)
        self.assertEqual(order.sms_logs.filter(template_type="RESERVATION_CONFIRMATION", status="DUMMY").count(), 1)
        self.assertEqual(order.sms_logs.get(template_type="RESERVATION_CONFIRMATION", status="DUMMY").created_by, self.manager)

    def test_card_requires_review_before_payment_and_pushes_cast_only_after_payment(self):
        self.store.card_payment_url = "https://payment.example"
        self.store.save(update_fields=["card_payment_url"])
        with patch("core.views.notify_cast_order") as push:
            order = self.accept_web(payment_method="CARD")
            self.assertFalse(order.sms_logs.filter(template_type="CARD_PAYMENT_REQUEST").exists())
            reviewed = self.op.post(f"/api/orders/{order.pk}/confirm/")
            self.assertEqual(reviewed.status_code, 200, reviewed.data)
            push.assert_not_called()
            self.assertEqual(order.sms_logs.filter(template_type="CARD_PAYMENT_REQUEST").count(), 1)
            paid = self.op.post(f"/api/orders/{order.pk}/confirm-card-payment/")
            self.assertEqual(paid.status_code, 200, paid.data)
            push.assert_called_once()
        self.assertEqual(self.op.post(f"/api/orders/{order.pk}/confirm-card-payment/").status_code, 400)

    def test_shift_override_only_relaxes_room_overlap(self):
        second = Cast.objects.create(store=self.store, name="交代担当")
        body = {"cast": second.pk, "room": self.room.pk, "date": self.business_date.isoformat(), "start_time": "13:00", "end_time": "15:00"}
        rejected = self.op.post("/api/shifts/", body, format="json")
        self.assertEqual(rejected.status_code, 400)
        self.assertIn("room_overlap", rejected.data)
        self.assertEqual(ShiftAssignment.objects.count(), 1)
        accepted = self.op.post("/api/shifts/", {**body, "allow_room_overlap": True}, format="json")
        self.assertEqual(accepted.status_code, 201, accepted.data)
        self.assertEqual(self.op.post("/api/shifts/", {**body, "allow_room_overlap": True}, format="json").status_code, 400)
        foreign = Room.objects.create(store=self.other_store, name="他店ルーム")
        self.assertEqual(self.op.patch(f"/api/shifts/{accepted.data['id']}/", {"room": foreign.pk, "allow_room_overlap": True}, format="json").status_code, 400)
        self.accept_web()
        customer = self.cast.store.customers.first()
        double_booking = self.op.post("/api/orders/", {
            "cast": second.pk, "room": self.room.pk, "customer": customer.pk,
            "course": self.course.pk, "start": "2030-01-15T13:00:00+09:00",
        }, format="json")
        self.assertEqual(double_booking.status_code, 400, double_booking.data)

    def test_cancellation_releases_pending_slot_and_denies_later_confirmation(self):
        order = self.accept_web()
        cancelled = self.op.post(f"/api/orders/{order.pk}/cancel/")
        self.assertEqual(cancelled.status_code, 200, cancelled.data)
        self.assertEqual(self.op.post(f"/api/orders/{order.pk}/confirm/").status_code, 400)
        self.assertEqual(self.op.post(f"/api/orders/{order.pk}/retry-booking-sms/").status_code, 400)
        slots = self.client.get("/api/public/booking/slots/", {"store": self.store.pk, "cast": self.cast.pk, "course": self.course.pk, "date": self.business_date.isoformat()})
        self.assertEqual(slots.status_code, 200)
        self.assertTrue(slots.data["slots"])

    def test_retry_and_notifications_are_store_and_role_scoped(self):
        order = self.accept_web()
        other = get_user_model().objects.create_user("other_manager")
        UserProfile.objects.create(user=other, store=self.other_store, role=UserProfile.Role.MANAGER)
        self.op.force_authenticate(other)
        self.assertEqual(self.op.post(f"/api/orders/{order.pk}/retry-booking-sms/").status_code, 404)
        self.assertEqual(self.op.get("/api/op/notifications/").data["notifications"], [])
        cast_user = get_user_model().objects.create_user("followup_cast")
        UserProfile.objects.create(user=cast_user, store=self.store, role=UserProfile.Role.CAST)
        self.op.force_authenticate(cast_user)
        self.assertEqual(self.op.post(f"/api/orders/{order.pk}/retry-booking-sms/").status_code, 403)

    def test_weekly_and_request_approval_can_confirm_room_overlap(self):
        second = Cast.objects.create(store=self.store, name="週次担当")
        payload = {"cast": second.pk, "week_start": "2030-01-14", "items": [{"date": "2030-01-15", "enabled": True, "room": self.room.pk, "start_time": "13:00", "end_time": "15:00"}]}
        rejected = self.op.post("/api/op/shifts/weekly/", payload, format="json")
        self.assertEqual(rejected.status_code, 400)
        self.assertIn("room_overlap", rejected.data["errors"][0])
        accepted = self.op.post("/api/op/shifts/weekly/", {**payload, "allow_room_overlap": True}, format="json")
        self.assertEqual(accepted.status_code, 201, accepted.data)
        third = Cast.objects.create(store=self.store, name="申請担当")
        request = ShiftRequest.objects.create(store=self.store, cast=third, date=self.business_date, start_time=time(13), end_time=time(15))
        url = f"/api/op/shift-requests/{request.pk}/approve/"
        body = {"room": self.room.pk}
        self.assertEqual(self.op.post(url, body, format="json").status_code, 400)
        approved = self.op.post(url, {**body, "allow_room_overlap": True}, format="json")
        self.assertEqual(approved.status_code, 200, approved.data)

    def test_sales_includes_zero_rows_and_keeps_filters_and_store_boundary(self):
        zero = Cast.objects.create(store=self.store, name="売上ゼロ", course_back_rate=50)
        foreign = Cast.objects.create(store=self.other_store, name="他店")
        data = get_sales_dashboard(self.store, self.business_date, self.business_date)
        self.assertEqual({r["cast_id"] for r in data["by_cast"]}, {self.cast.pk, zero.pk})
        self.assertTrue(all(r["sales"] == r["estimated_pay"] == r["orders"] == 0 for r in data["by_cast"]))
        filtered = get_sales_dashboard(self.store, self.business_date, self.business_date, cast_id=zero.pk)
        self.assertEqual([r["cast_id"] for r in filtered["by_cast"]], [zero.pk])
        self.assertEqual(get_sales_dashboard(self.store, self.business_date, self.business_date, cast_id=foreign.pk)["by_cast"], [])
        self.assertIn("売上ゼロ", get_sales_dashboard_csv(self.store, self.business_date, self.business_date))
