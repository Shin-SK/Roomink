from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import (
    Cast, Course, Customer, Order, OrderGuestAccess, Room, SmsLog, Store,
    StorePhoneNumber, UserProfile,
)


User = get_user_model()


@override_settings(
    RESERVATION_LINK_BASE_URL="https://r.roomink.net",
    SMS_DUMMY_MODE=True,
)
class GuestReservationFlowTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(
            name="ゲスト予約テスト店",
            slug="guest-reservation-test",
            card_payment_url="https://pay.example/store",
        )
        self.manager = User.objects.create_user("guest_flow_manager")
        UserProfile.objects.create(
            user=self.manager,
            store=self.store,
            role=UserProfile.Role.MANAGER,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.manager)
        self.public_client = APIClient()
        self.cast = Cast.objects.create(store=self.store, name="ゲスト予約キャスト")
        self.room = Room.objects.create(
            store=self.store,
            name="101",
            address="東京都テスト区1-2-3",
            map_url="https://maps.example/101",
            sms_notice="建物名をご確認ください。",
        )
        self.customer = Customer.objects.create(
            store=self.store,
            display_name="ゲスト予約顧客",
            phone="09000000001",
        )
        self.course = Course.objects.create(
            store=self.store,
            name="60分",
            duration=60,
            price=12000,
        )
        StorePhoneNumber.objects.create(
            store=self.store,
            phone="+15551234567",
            source_phone="0312345678",
            label="予約受付",
            is_active=True,
        )

    def create_order(self, payment_method):
        start = timezone.now() + timedelta(days=2)
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
            end=start + timedelta(hours=1),
            status=Order.Status.REQUESTED,
            payment_method=payment_method,
        )

    def guest_response(self, order):
        access = OrderGuestAccess.objects.get(order=order)
        response = self.public_client.get(f"/api/public/reservations/{access.token}/")
        self.assertEqual(response.status_code, 200, response.data)
        return access, response

    def test_cash_confirmation_sends_one_segment_and_reveals_confirmed_room(self):
        order = self.create_order(Order.PaymentMethod.CASH)

        confirmed = self.client.post(f"/api/orders/{order.id}/confirm/")

        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        customer_logs = SmsLog.objects.filter(
            order=order,
            template_type=SmsLog.TemplateType.RESERVATION_CONFIRMATION,
        )
        self.assertEqual(customer_logs.count(), 1)
        log = customer_logs.get()
        self.assertEqual(log.encoding, "UCS-2")
        self.assertEqual(log.segment_count, 1)
        self.assertIn("[予約リンク]", log.body)
        access, guest = self.guest_response(order)
        self.assertEqual(guest.data["state"], "CONFIRMED")
        self.assertEqual(guest.data["room_address"], self.room.address)
        self.assertEqual(guest.data["payment_method_label"], "現金")
        self.assertEqual(guest.data["contact_phone"], "0312345678")
        access.refresh_from_db()
        self.assertEqual(access.open_count, 1)
        self.assertEqual(access.last_seen_state, "CONFIRMED")

    def test_cti_number_is_not_exposed_without_store_reception_number(self):
        StorePhoneNumber.objects.filter(store=self.store).update(source_phone="")
        order = self.create_order(Order.PaymentMethod.CASH)
        self.assertEqual(self.client.post(f"/api/orders/{order.id}/confirm/").status_code, 200)

        _, guest = self.guest_response(order)

        self.assertEqual(guest.data["contact_phone"], "")

    def test_card_flow_hides_room_until_manual_confirmation_and_uses_two_segments_total(self):
        order = self.create_order(Order.PaymentMethod.CARD)

        first = self.client.post(f"/api/orders/{order.id}/confirm/")

        self.assertEqual(first.status_code, 200, first.data)
        access, pending = self.guest_response(order)
        self.assertEqual(pending.data["state"], "PAYMENT_REQUIRED")
        self.assertEqual(pending.data["room_address"], "")
        self.assertEqual(pending.data["payment_url"], self.store.card_payment_url)
        first_log = SmsLog.objects.get(
            order=order,
            template_type=SmsLog.TemplateType.CARD_PAYMENT_REQUEST,
        )
        self.assertEqual(first_log.segment_count, 1)

        second = self.client.post(f"/api/orders/{order.id}/confirm-card-payment/")

        self.assertEqual(second.status_code, 200, second.data)
        access.refresh_from_db()
        self.assertEqual(OrderGuestAccess.objects.get(order=order).pk, access.pk)
        confirmed = self.public_client.get(f"/api/public/reservations/{access.token}/")
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        self.assertEqual(confirmed.data["state"], "CONFIRMED")
        self.assertEqual(confirmed.data["payment_url"], "")
        self.assertEqual(confirmed.data["room_address"], self.room.address)
        second_log = SmsLog.objects.get(
            order=order,
            template_type=SmsLog.TemplateType.CARD_PAYMENT_CONFIRMED,
        )
        self.assertEqual(second_log.segment_count, 1)
        self.assertEqual(
            sum(SmsLog.objects.filter(order=order).exclude(
                template_type=SmsLog.TemplateType.CAST_NOTICE,
            ).values_list("segment_count", flat=True)),
            2,
        )

    def test_cancelled_reservation_keeps_same_link_and_adds_cancelled_timeline(self):
        order = self.create_order(Order.PaymentMethod.CASH)
        self.assertEqual(self.client.post(f"/api/orders/{order.id}/confirm/").status_code, 200)
        access = OrderGuestAccess.objects.get(order=order)

        cancelled = self.client.post(f"/api/orders/{order.id}/cancel/")

        self.assertEqual(cancelled.status_code, 200, cancelled.data)
        guest = self.public_client.get(f"/api/public/reservations/{access.token}/")
        self.assertEqual(guest.status_code, 200, guest.data)
        self.assertEqual(guest.data["state"], "CANCELLED")
        self.assertEqual(guest.data["room_address"], "")
        self.assertEqual(guest.data["timeline"][-1]["type"], "CANCELLED")
        cancelled_log = SmsLog.objects.get(
            order=order,
            template_type=SmsLog.TemplateType.RESERVATION_CANCELLED,
        )
        self.assertEqual(cancelled_log.segment_count, 1)

    def test_invalid_expired_and_invalidated_tokens_are_not_disclosed(self):
        order = self.create_order(Order.PaymentMethod.CASH)
        self.assertEqual(self.client.post(f"/api/orders/{order.id}/confirm/").status_code, 200)
        access = OrderGuestAccess.objects.get(order=order)

        invalid = self.public_client.get("/api/public/reservations/not-a-real-token/")
        access.expires_at = timezone.now() - timedelta(seconds=1)
        access.save(update_fields=["expires_at"])
        expired = self.public_client.get(f"/api/public/reservations/{access.token}/")
        access.expires_at = timezone.now() + timedelta(days=1)
        access.invalidated_at = timezone.now()
        access.save(update_fields=["expires_at", "invalidated_at"])
        invalidated = self.public_client.get(f"/api/public/reservations/{access.token}/")

        self.assertEqual(invalid.status_code, 404)
        self.assertEqual(expired.status_code, 404)
        self.assertEqual(invalidated.status_code, 404)
        self.assertEqual(invalid.json(), expired.json())
        self.assertEqual(expired.json(), invalidated.json())


@override_settings(
    DEBUG=True,
    TWILIO_WEBHOOK_ALLOW_UNSIGNED=True,
    TWILIO_ACCOUNT_SID="ACtest",
    TWILIO_AUTH_TOKEN="test-token",
)
class SmsDeliveryStatusWebhookTest(TestCase):
    def test_terminal_callback_updates_delivery_and_actual_segments(self):
        log = SmsLog.objects.create(
            to_phone="09000000001",
            body="[予約リンク]",
            status=SmsLog.Status.SENT,
            provider=SmsLog.Provider.TWILIO,
            provider_message_id="SMtest",
            provider_status="queued",
            encoding="UCS-2",
            segment_count=1,
        )
        fetched_message = MagicMock(num_segments="2")
        client = MagicMock()
        client.messages.return_value.fetch.return_value = fetched_message

        with patch("twilio.rest.Client", return_value=client):
            response = APIClient().post(
                "/api/webhook/twilio/sms-status/",
                {"MessageSid": "SMtest", "MessageStatus": "delivered"},
                format="multipart",
            )

        self.assertEqual(response.status_code, 200)
        log.refresh_from_db()
        self.assertEqual(log.provider_status, "delivered")
        self.assertEqual(log.segment_count, 2)
        self.assertIsNotNone(log.delivered_at)
