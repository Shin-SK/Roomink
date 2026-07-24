import hashlib
import re
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import (
    Cast,
    Course,
    Customer,
    CustomerAccountInvitation,
    Order,
    Room,
    SmsLog,
    Store,
    UserProfile,
)
from core.services.notify import send_sms
from core.services.customer_invitation import issue_customer_invitation


User = get_user_model()


@override_settings(
    FRONTEND_URL="https://roomink.example",
    SMS_DUMMY_MODE=True,
)
class CustomerInvitationFlowTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="招待テスト店舗")
        self.other_store = Store.objects.create(name="他店舗")
        self.manager = User.objects.create_user("invite_manager", password="manager-pass-123")
        UserProfile.objects.create(
            user=self.manager,
            store=self.store,
            role=UserProfile.Role.MANAGER,
        )
        self.cast_user = User.objects.create_user("invite_cast", password="cast-pass-123")
        UserProfile.objects.create(
            user=self.cast_user,
            store=self.store,
            role=UserProfile.Role.CAST,
        )
        self.cast = Cast.objects.create(store=self.store, user=self.cast_user, name="招待テストキャスト")
        self.room = Room.objects.create(store=self.store, name="招待テスト部屋")
        self.course = Course.objects.create(
            store=self.store,
            name="60分",
            duration=60,
            price=10000,
        )
        self.customer = Customer.objects.create(
            store=self.store,
            phone="090-1234-5678",
            display_name="招待テスト顧客",
        )
        start = timezone.now() + timedelta(days=1)
        self.order = Order.objects.create(
            store=self.store,
            cast=self.cast,
            room=self.room,
            customer=self.customer,
            course=self.course,
            course_name=self.course.name,
            course_price=self.course.price,
            total_price=self.course.price,
            start=start,
            end=start + timedelta(minutes=60),
            status=Order.Status.REQUESTED,
            payment_method=Order.PaymentMethod.CASH,
        )
        self.manager_client = APIClient()
        self.manager_client.force_authenticate(self.manager)

    def _confirm_and_get_token(self):
        bodies = []

        def capture_sms(*args, **kwargs):
            body = kwargs.get("body", "")
            bodies.append(body)
            return send_sms(*args, **kwargs)

        with patch("core.services.notify.TWILIO_ACCOUNT_SID", ""), \
             patch("core.services.notify.TWILIO_AUTH_TOKEN", ""), \
             patch("core.services.notify.TWILIO_FROM_PHONE", ""), \
             patch("core.services.notify.send_sms", side_effect=capture_sms):
            response = self.manager_client.post(f"/api/orders/{self.order.id}/confirm/")

        self.assertEqual(response.status_code, 200, response.data)
        activation_body = next(body for body in bodies if "/cu/activate?token=" in body)
        match = re.search(r"/cu/activate\?token=([^\s]+)", activation_body)
        self.assertIsNotNone(match)
        return match.group(1), activation_body

    def test_public_signup_is_disabled_and_never_changes_database(self):
        before = (User.objects.count(), Customer.objects.count())
        existing = APIClient().post(
            "/api/cu/signup/",
            {
                "store_id": self.store.id,
                "phone": self.customer.phone,
                "password": "new-password-123",
                "display_name": "第三者",
            },
            format="json",
        )
        missing = APIClient().post(
            "/api/cu/signup/",
            {
                "store_id": self.store.id,
                "phone": "09099999999",
                "password": "new-password-123",
                "display_name": "未登録",
            },
            format="json",
        )
        self.assertEqual(existing.status_code, 410)
        self.assertEqual(missing.status_code, 410)
        self.assertEqual(existing.json(), missing.json())
        self.assertEqual((User.objects.count(), Customer.objects.count()), before)
        self.customer.refresh_from_db()
        self.assertIsNone(self.customer.user_id)

    def test_confirmation_issues_hashed_one_time_invitation_and_redacts_persisted_sms(self):
        token, sent_body = self._confirm_and_get_token()
        invitation = CustomerAccountInvitation.objects.get(customer=self.customer)
        self.assertEqual(invitation.order_id, self.order.id)
        self.assertEqual(invitation.token_hash, hashlib.sha256(token.encode()).hexdigest())
        self.assertNotIn(token, invitation.token_hash)
        self.assertGreater(invitation.expires_at, timezone.now() + timedelta(hours=71))
        self.assertLessEqual(invitation.expires_at, timezone.now() + timedelta(hours=73))
        self.assertIn("https://roomink.example/cu/activate?token=", sent_body)

        log = SmsLog.objects.get(
            order=self.order,
            template_type=SmsLog.TemplateType.RESERVATION_CONFIRMATION,
        )
        self.assertEqual(log.status, SmsLog.Status.DUMMY)
        self.assertNotIn(token, log.body)
        self.assertNotIn("09012345678", log.body)

    def test_valid_invitation_sets_password_links_customer_and_logs_in(self):
        token, _ = self._confirm_and_get_token()
        anonymous = APIClient()

        self.assertEqual(anonymous.get("/api/cu/activate/", {"token": token}).status_code, 405)
        preview = anonymous.post(
            "/api/cu/activate/preview/",
            {"token": token},
            format="json",
        )
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertEqual(preview.data["masked_phone"], "***5678")

        activated = anonymous.post(
            "/api/cu/activate/",
            {
                "token": token,
                "password": "safe-customer-pass-123",
                "password_confirm": "safe-customer-pass-123",
            },
            format="json",
        )
        self.assertEqual(activated.status_code, 200, activated.data)
        self.customer.refresh_from_db()
        self.assertIsNotNone(self.customer.user_id)
        self.assertTrue(self.customer.user.check_password("safe-customer-pass-123"))
        invitation = CustomerAccountInvitation.objects.get(customer=self.customer)
        self.assertIsNotNone(invitation.used_at)

        me = anonymous.get("/api/auth/me/")
        self.assertEqual(me.status_code, 200, me.data)
        self.assertEqual(me.data["role"], "customer")
        self.assertEqual(me.data["roles"], ["customer"])
        self.assertIn(f"/cu/reservations/{self.order.id}", activated.data["next"])

    def test_invalid_expired_and_used_tokens_share_generic_response_and_do_not_mutate(self):
        token, _ = self._confirm_and_get_token()
        invitation = CustomerAccountInvitation.objects.get(customer=self.customer)
        invitation.expires_at = timezone.now() - timedelta(seconds=1)
        invitation.save(update_fields=["expires_at"])

        invalid = APIClient().post(
            "/api/cu/activate/",
            {"token": "not-a-real-token", "password": "safe-pass-123", "password_confirm": "safe-pass-123"},
            format="json",
        )
        expired = APIClient().post(
            "/api/cu/activate/",
            {"token": token, "password": "safe-pass-123", "password_confirm": "safe-pass-123"},
            format="json",
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(expired.status_code, 400)
        self.assertEqual(invalid.json(), expired.json())
        self.customer.refresh_from_db()
        self.assertIsNone(self.customer.user_id)
        self.assertEqual(User.objects.filter(username="09012345678").count(), 0)

        invitation.expires_at = timezone.now() + timedelta(hours=1)
        invitation.save(update_fields=["expires_at"])
        valid = APIClient().post(
            "/api/cu/activate/",
            {"token": token, "password": "safe-pass-123", "password_confirm": "safe-pass-123"},
            format="json",
        )
        self.assertEqual(valid.status_code, 200)
        used = APIClient().post(
            "/api/cu/activate/",
            {"token": token, "password": "another-safe-pass-123", "password_confirm": "another-safe-pass-123"},
            format="json",
        )
        self.assertEqual(used.status_code, 400)
        self.assertEqual(used.json(), invalid.json())
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.user.check_password("safe-pass-123"))

    def test_password_validation_failure_leaves_invitation_unused(self):
        token, _ = self._confirm_and_get_token()
        response = APIClient().post(
            "/api/cu/activate/",
            {"token": token, "password": "12345678", "password_confirm": "12345678"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        invitation = CustomerAccountInvitation.objects.get(customer=self.customer)
        self.assertIsNone(invitation.used_at)
        self.customer.refresh_from_db()
        self.assertIsNone(self.customer.user_id)

    def test_reissue_invalidates_previous_token_and_is_store_scoped(self):
        old_token, _ = self._confirm_and_get_token()
        with patch("core.services.notify.TWILIO_ACCOUNT_SID", ""), \
             patch("core.services.notify.TWILIO_AUTH_TOKEN", ""), \
             patch("core.services.notify.TWILIO_FROM_PHONE", ""):
            response = self.manager_client.post(
                f"/api/op/customers/{self.customer.id}/invitation/",
                {},
                format="json",
            )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn("token", response.data)
        self.assertNotIn("url", response.data)
        self.assertEqual(CustomerAccountInvitation.objects.filter(customer=self.customer).count(), 2)
        old = CustomerAccountInvitation.objects.order_by("created_at").first()
        self.assertIsNotNone(old.invalidated_at)

        rejected = APIClient().post(
            "/api/cu/activate/",
            {"token": old_token, "password": "safe-pass-123", "password_confirm": "safe-pass-123"},
            format="json",
        )
        self.assertEqual(rejected.status_code, 400)

        other_manager = User.objects.create_user("other_manager", password="other-pass-123")
        UserProfile.objects.create(
            user=other_manager,
            store=self.other_store,
            role=UserProfile.Role.MANAGER,
        )
        other_client = APIClient()
        other_client.force_authenticate(other_manager)
        self.assertEqual(
            other_client.get(f"/api/op/customers/{self.customer.id}/invitation/").status_code,
            404,
        )

    def test_repeated_confirmation_does_not_create_another_invitation(self):
        self._confirm_and_get_token()
        second = self.manager_client.post(f"/api/orders/{self.order.id}/confirm/")
        self.assertEqual(second.status_code, 400)
        self.assertEqual(CustomerAccountInvitation.objects.filter(customer=self.customer).count(), 1)

    def test_second_store_invitation_can_link_the_same_verified_user(self):
        first_token, _ = self._confirm_and_get_token()
        first_client = APIClient()
        activated = first_client.post(
            "/api/cu/activate/",
            {"token": first_token, "password": "shared-safe-pass-123", "password_confirm": "shared-safe-pass-123"},
            format="json",
        )
        self.assertEqual(activated.status_code, 200)
        self.customer.refresh_from_db()
        shared_user = self.customer.user

        other_customer = Customer.objects.create(
            store=self.other_store,
            phone="09012345678",
            display_name="同一人物・別店舗",
        )
        _, second_token = issue_customer_invitation(other_customer)
        second_client = APIClient()
        linked = second_client.post(
            "/api/cu/activate/",
            {"token": second_token, "password": "shared-safe-pass-123", "password_confirm": "shared-safe-pass-123"},
            format="json",
        )
        self.assertEqual(linked.status_code, 200, linked.data)
        other_customer.refresh_from_db()
        self.assertEqual(other_customer.user_id, shared_user.id)
        self.assertEqual(User.objects.filter(customer_profiles__phone__endswith="5678").distinct().count(), 1)

    def test_customer_phone_login_supports_existing_non_phone_username(self):
        customer_user = User.objects.create_user("legacy_customer", password="legacy-pass-123")
        self.customer.user = customer_user
        self.customer.save(update_fields=["user"])

        client = APIClient()
        response = client.post(
            "/api/cu/login/",
            {"phone": "090-1234-5678", "password": "legacy-pass-123"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        me = client.get("/api/auth/me/")
        self.assertEqual(me.status_code, 200, me.data)
        self.assertEqual(me.data["role"], "customer")

    def test_customer_phone_login_rejects_ambiguous_accounts_without_enumeration(self):
        first_user = User.objects.create_user("first_customer", password="same-pass-123")
        second_user = User.objects.create_user("second_customer", password="same-pass-123")
        self.customer.user = first_user
        self.customer.save(update_fields=["user"])
        Customer.objects.create(
            store=self.other_store,
            phone="09012345678",
            display_name="別店舗顧客",
            user=second_user,
        )

        ambiguous = APIClient().post(
            "/api/cu/login/",
            {"phone": "09012345678", "password": "same-pass-123"},
            format="json",
        )
        missing = APIClient().post(
            "/api/cu/login/",
            {"phone": "09000000000", "password": "same-pass-123"},
            format="json",
        )
        self.assertEqual(ambiguous.status_code, 401)
        self.assertEqual(missing.status_code, 401)
        self.assertEqual(ambiguous.json(), missing.json())

    def test_customer_cannot_access_operator_or_cast_endpoints(self):
        customer_user = User.objects.create_user("customer_only", password="customer-pass-123")
        self.customer.user = customer_user
        self.customer.save(update_fields=["user"])
        client = APIClient()
        client.force_authenticate(customer_user)

        self.assertEqual(client.get("/api/orders/").status_code, 403)
        self.assertEqual(client.get("/api/cast/today/").status_code, 403)
        self.assertEqual(client.get("/api/cu/mypage/").status_code, 200)

    def test_manager_and_cast_login_paths_are_unchanged(self):
        for username, password, role in (
            ("invite_manager", "manager-pass-123", "manager"),
            ("invite_cast", "cast-pass-123", "cast"),
        ):
            client = APIClient()
            logged_in = client.post(
                "/api/auth/login/",
                {"username": username, "password": password},
                format="json",
            )
            self.assertEqual(logged_in.status_code, 200)
            me = client.get("/api/auth/me/")
            self.assertEqual(me.status_code, 200)
            self.assertEqual(me.data["role"], role)

    def test_registered_customer_gets_login_link_without_invitation(self):
        user = User.objects.create_user("registered_customer", password="registered-pass-123")
        self.customer.user = user
        self.customer.save(update_fields=["user"])
        token_bodies = []

        def capture_sms(*args, **kwargs):
            token_bodies.append(kwargs.get("body", ""))
            return send_sms(*args, **kwargs)

        with patch("core.services.notify.TWILIO_ACCOUNT_SID", ""), \
             patch("core.services.notify.TWILIO_AUTH_TOKEN", ""), \
             patch("core.services.notify.TWILIO_FROM_PHONE", ""), \
             patch("core.services.notify.send_sms", side_effect=capture_sms):
            response = self.manager_client.post(f"/api/orders/{self.order.id}/confirm/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(CustomerAccountInvitation.objects.filter(customer=self.customer).count(), 0)
        customer_body = next(body for body in token_bodies if body.startswith("【Roomink】ご予約"))
        self.assertIn("/cu/login?", customer_body)
        self.assertNotIn("/cu/activate?", customer_body)

    @override_settings(FRONTEND_URL="")
    def test_missing_frontend_url_fails_closed_without_creating_invitation(self):
        with patch("core.services.notify.TWILIO_ACCOUNT_SID", ""), \
             patch("core.services.notify.TWILIO_AUTH_TOKEN", ""), \
             patch("core.services.notify.TWILIO_FROM_PHONE", ""):
            response = self.manager_client.post(f"/api/orders/{self.order.id}/confirm/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CustomerAccountInvitation.objects.filter(customer=self.customer).exists())
        log = SmsLog.objects.get(
            order=self.order,
            template_type=SmsLog.TemplateType.RESERVATION_CONFIRMATION,
        )
        self.assertEqual(log.status, SmsLog.Status.CONFIG_MISSING)
