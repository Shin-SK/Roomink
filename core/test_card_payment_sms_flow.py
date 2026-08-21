from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Cast, Course, Customer, Order, Room, SmsLog, SmsTemplate, Store, UserProfile


User = get_user_model()


@override_settings(FRONTEND_URL="https://roomink.example", SMS_DUMMY_MODE=True)
class CardPaymentSmsFlowTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(
            name="カードSMSテスト店",
            slug="card-sms-test",
            card_payment_url="https://pay.example/roomink-store",
        )
        self.other_store = Store.objects.create(name="別店舗", slug="card-sms-other")
        self.manager = self.create_operator("card_sms_manager", UserProfile.Role.MANAGER)
        self.staff = self.create_operator("card_sms_staff", UserProfile.Role.STAFF)
        self.manager_client = self.authenticated_client(self.manager)
        self.staff_client = self.authenticated_client(self.staff)
        self.cast = Cast.objects.create(store=self.store, name="カードSMSキャスト")
        self.room = Room.objects.create(
            store=self.store,
            name="新宿101",
            address="東京都新宿区1-2-3",
            map_url="https://maps.example/shinjuku101",
            sms_notice="入口を間違えないようご注意ください。",
        )
        self.customer = Customer.objects.create(
            store=self.store,
            display_name="カードSMS顧客",
            phone="09012345678",
        )
        self.course = Course.objects.create(
            store=self.store,
            name="120分コース",
            duration=120,
            price=20000,
        )

    def create_operator(self, username, role):
        user = User.objects.create_user(username)
        UserProfile.objects.create(user=user, store=self.store, role=role)
        return user

    def authenticated_client(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def create_order(self, payment_method=Order.PaymentMethod.CARD, room=True, status=Order.Status.REQUESTED):
        start = timezone.now() + timedelta(days=2)
        return Order.objects.create(
            store=self.store,
            cast=self.cast,
            room=self.room if room else None,
            customer=self.customer,
            course=self.course,
            course_name=self.course.name,
            course_price=self.course.price,
            total_price=self.course.price,
            start=start,
            end=start + timedelta(hours=2),
            status=status,
            payment_method=payment_method,
        )

    def test_settings_are_store_scoped_and_include_two_card_stages(self):
        response = self.manager_client.put(
            "/api/op/sms-templates/",
            {
                "card_payment_url": "https://pay.example/rs-spa",
                "items": [
                    {
                        "template_type": SmsTemplate.TemplateType.CARD_PAYMENT_REQUEST,
                        "payment_method": Order.PaymentMethod.CARD,
                        "body": "決済URL: {payment_url}",
                        "is_active": True,
                    },
                    {
                        "template_type": SmsTemplate.TemplateType.CARD_PAYMENT_CONFIRMED,
                        "payment_method": Order.PaymentMethod.CARD,
                        "body": "決済確認済み\n{room_guidance}",
                        "is_active": True,
                    },
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["card_payment_url"], "https://pay.example/rs-spa")
        card_types = {
            item["template_type"]
            for item in response.data["items"]
            if item["payment_method"] == Order.PaymentMethod.CARD
        }
        self.assertEqual(card_types, {
            SmsTemplate.TemplateType.CARD_PAYMENT_REQUEST,
            SmsTemplate.TemplateType.CARD_PAYMENT_CONFIRMED,
        })
        self.store.refresh_from_db()
        self.other_store.refresh_from_db()
        self.assertEqual(self.store.card_payment_url, "https://pay.example/rs-spa")
        self.assertEqual(self.other_store.card_payment_url, "")

        forbidden = self.staff_client.put(
            "/api/op/sms-templates/",
            {"card_payment_url": "https://pay.example/forbidden", "items": []},
            format="json",
        )
        self.assertEqual(forbidden.status_code, 403, forbidden.data)

    def test_card_reservation_sends_link_then_confirm_action_sends_room_guidance(self):
        order = self.create_order()

        confirmed = self.manager_client.post(f"/api/orders/{order.id}/confirm/")

        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        first_log = SmsLog.objects.get(
            order=order,
            template_type=SmsLog.TemplateType.CARD_PAYMENT_REQUEST,
        )
        self.assertEqual(first_log.status, SmsLog.Status.DUMMY)
        self.assertIn(self.store.card_payment_url, first_log.body)
        self.assertNotIn(self.room.address, first_log.body)
        self.assertNotIn("/cu/", first_log.body)

        second = self.manager_client.post(f"/api/orders/{order.id}/confirm-card-payment/")

        self.assertEqual(second.status_code, 200, second.data)
        order.refresh_from_db()
        self.assertIsNotNone(order.card_payment_confirmed_at)
        self.assertEqual(order.card_payment_confirmed_by, self.manager)
        second_log = SmsLog.objects.get(
            order=order,
            template_type=SmsLog.TemplateType.CARD_PAYMENT_CONFIRMED,
        )
        self.assertEqual(second_log.status, SmsLog.Status.DUMMY)
        self.assertIn(self.room.address, second_log.body)
        self.assertIn(self.room.map_url, second_log.body)
        self.assertIn(self.room.sms_notice, second_log.body)

        duplicate = self.manager_client.post(f"/api/orders/{order.id}/confirm-card-payment/")
        self.assertEqual(duplicate.status_code, 400, duplicate.data)
        self.assertEqual(
            SmsLog.objects.filter(
                order=order,
                template_type=SmsLog.TemplateType.CARD_PAYMENT_CONFIRMED,
            ).count(),
            1,
        )

    def test_missing_payment_url_fails_closed_without_sending_card_link(self):
        self.store.card_payment_url = ""
        self.store.save(update_fields=["card_payment_url"])
        order = self.create_order()

        response = self.manager_client.post(f"/api/orders/{order.id}/confirm/")

        self.assertEqual(response.status_code, 200, response.data)
        log = SmsLog.objects.get(
            order=order,
            template_type=SmsLog.TemplateType.CARD_PAYMENT_REQUEST,
        )
        self.assertEqual(log.status, SmsLog.Status.CONFIG_MISSING)
        self.assertEqual(log.error_message, "CARD_PAYMENT_URL_MISSING")

    def test_second_sms_rejects_non_card_and_room_pending_without_updates(self):
        cash_order = self.create_order(
            payment_method=Order.PaymentMethod.CASH,
            status=Order.Status.CONFIRMED,
        )
        room_pending = self.create_order(room=False, status=Order.Status.CONFIRMED)

        cash_response = self.manager_client.post(
            f"/api/orders/{cash_order.id}/confirm-card-payment/",
        )
        pending_response = self.manager_client.post(
            f"/api/orders/{room_pending.id}/confirm-card-payment/",
        )

        self.assertEqual(cash_response.status_code, 400, cash_response.data)
        self.assertEqual(pending_response.status_code, 400, pending_response.data)
        cash_order.refresh_from_db()
        room_pending.refresh_from_db()
        self.assertIsNone(cash_order.card_payment_confirmed_at)
        self.assertIsNone(room_pending.card_payment_confirmed_at)
        self.assertFalse(SmsLog.objects.filter(
            template_type=SmsLog.TemplateType.CARD_PAYMENT_CONFIRMED,
        ).exists())
