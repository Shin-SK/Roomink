from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import (
    Customer,
    Store,
    SystemAnnouncement,
    SystemAnnouncementReadReceipt,
    UserProfile,
)
from core.serializers import CastAccountProvisionSerializer, StaffCreateSerializer


User = get_user_model()


class StoreCatalogPrivacyTest(TestCase):
    def test_anonymous_users_cannot_retrieve_a_store_catalog(self):
        Store.objects.create(name="非公開店舗A")
        Store.objects.create(name="非公開店舗B")

        response = APIClient().get("/api/cu/store-list/")

        self.assertEqual(response.status_code, 404)
        self.assertNotIn("非公開店舗A", response.content.decode())
        self.assertNotIn("非公開店舗B", response.content.decode())


class CloudflareOriginLockTest(TestCase):
    @override_settings(
        CLOUDFLARE_ORIGIN_LOCK_ENABLED=True,
        CLOUDFLARE_ORIGIN_SECRET="test-origin-secret",
    )
    def test_rejects_direct_heroku_access_without_the_edge_secret(self):
        response = APIClient().get("/api/health/")

        self.assertEqual(response.status_code, 403)

    @override_settings(
        CLOUDFLARE_ORIGIN_LOCK_ENABLED=True,
        CLOUDFLARE_ORIGIN_SECRET="test-origin-secret",
    )
    def test_allows_requests_forwarded_by_cloudflare(self):
        response = APIClient().get(
            "/api/health/",
            HTTP_X_ROOMINK_ORIGIN_SECRET="test-origin-secret",
        )

        self.assertEqual(response.status_code, 200)

    @override_settings(
        CLOUDFLARE_ORIGIN_LOCK_ENABLED=True,
        CLOUDFLARE_ORIGIN_SECRET="test-origin-secret",
    )
    def test_rejects_a_wrong_edge_secret(self):
        response = APIClient().get(
            "/api/health/",
            HTTP_X_ROOMINK_ORIGIN_SECRET="wrong-secret",
        )

        self.assertEqual(response.status_code, 403)


class PasswordPolicyCompatibilityTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="セキュリティ検証店")

    def _operator(self, username, password, role):
        user = User.objects.create_user(username=username, password=password)
        UserProfile.objects.create(user=user, store=self.store, role=role)
        return user

    def test_existing_weak_password_is_not_forcibly_rejected(self):
        self._operator("existing-cast", "1234", UserProfile.Role.CAST)
        client = APIClient()

        response = client.post(
            "/api/auth/login/",
            {"username": "existing-cast", "password": "1234"},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(client.get("/api/auth/me/").status_code, 200)

    def test_new_staff_password_uses_ten_character_floor(self):
        weak = StaffCreateSerializer(data={
            "username": "new-staff",
            "password": "Abc12345",
            "role": UserProfile.Role.STAFF,
        })
        self.assertFalse(weak.is_valid())
        self.assertIn("10文字以上", str(weak.errors["password"]))

        acceptable = StaffCreateSerializer(data={
            "username": "new-staff",
            "password": "River8Moon!",
            "role": UserProfile.Role.STAFF,
        })
        self.assertTrue(acceptable.is_valid(), acceptable.errors)

    def test_new_cast_password_keeps_eight_character_floor(self):
        weak = CastAccountProvisionSerializer(data={
            "username": "new-cast",
            "password": "Abc1234",
        })
        self.assertFalse(weak.is_valid())

        acceptable = CastAccountProvisionSerializer(data={
            "username": "new-cast",
            "password": "River829",
        })
        self.assertTrue(acceptable.is_valid(), acceptable.errors)

    def test_password_change_keeps_current_session_and_ends_other_sessions(self):
        self._operator("manager", "old-pass", UserProfile.Role.MANAGER)
        current = APIClient()
        other = APIClient()
        for client in (current, other):
            login_response = client.post(
                "/api/auth/login/",
                {"username": "manager", "password": "old-pass"},
                format="json",
            )
            self.assertEqual(login_response.status_code, 200)

        response = current.post(
            "/api/auth/change-password/",
            {
                "current_password": "old-pass",
                "new_password": "River8Moon!",
                "new_password_confirm": "River8Moon!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(current.get("/api/auth/me/").status_code, 200)
        self.assertEqual(other.get("/api/auth/me/").status_code, 403)

    def test_role_based_session_lifetimes_are_applied_at_login(self):
        self._operator("staff", "old-pass", UserProfile.Role.STAFF)
        self._operator("cast", "old-pass", UserProfile.Role.CAST)

        staff = APIClient()
        cast = APIClient()
        self.assertEqual(
            staff.post("/api/auth/login/", {"username": "staff", "password": "old-pass"}, format="json").status_code,
            200,
        )
        self.assertEqual(
            cast.post("/api/auth/login/", {"username": "cast", "password": "old-pass"}, format="json").status_code,
            200,
        )

        self.assertAlmostEqual(staff.session.get_expiry_age(), 14 * 24 * 60 * 60, delta=5)
        self.assertAlmostEqual(cast.session.get_expiry_age(), 90 * 24 * 60 * 60, delta=5)


class LoginCsrfProtectionTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="CSRF検証店")
        self.operator = User.objects.create_user(username="operator", password="operator-pass")
        UserProfile.objects.create(
            user=self.operator,
            store=self.store,
            role=UserProfile.Role.STAFF,
        )
        self.customer_user = User.objects.create_user(
            username="customer",
            password="customer-pass",
        )
        Customer.objects.create(
            store=self.store,
            user=self.customer_user,
            phone="09011112222",
            display_name="顧客",
        )

    def _csrf_token(self, client):
        response = client.get("/api/auth/csrf/")
        return response.cookies["csrftoken"].value

    def test_operator_login_requires_csrf_token(self):
        client = APIClient(enforce_csrf_checks=True)
        payload = {"username": "operator", "password": "operator-pass"}
        self.assertEqual(client.post("/api/auth/login/", payload, format="json").status_code, 403)

        token = self._csrf_token(client)
        response = client.post(
            "/api/auth/login/",
            payload,
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 200, response.data)

    def test_customer_login_requires_csrf_token(self):
        client = APIClient(enforce_csrf_checks=True)
        payload = {"phone": "09011112222", "password": "customer-pass"}
        self.assertEqual(client.post("/api/cu/login/", payload, format="json").status_code, 403)

        token = self._csrf_token(client)
        response = client.post(
            "/api/cu/login/",
            payload,
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 200, response.data)


class LoginLockoutTest(TestCase):
    def setUp(self):
        store = Store.objects.create(name="ロックアウト検証店")
        user = User.objects.create_user(username="locked-user", password="correct-pass")
        UserProfile.objects.create(user=user, store=store, role=UserProfile.Role.STAFF)

    @override_settings(AXES_FAILURE_LIMIT=3)
    def test_repeated_failure_temporarily_blocks_even_the_correct_password(self):
        client = APIClient()
        wrong = {"username": "locked-user", "password": "wrong-pass"}
        request_kwargs = {"format": "json", "REMOTE_ADDR": "198.51.100.10"}

        self.assertEqual(client.post("/api/auth/login/", wrong, **request_kwargs).status_code, 401)
        self.assertEqual(client.post("/api/auth/login/", wrong, **request_kwargs).status_code, 401)
        locked = client.post("/api/auth/login/", wrong, **request_kwargs)
        self.assertEqual(locked.status_code, 429, locked.content)

        still_locked = client.post(
            "/api/auth/login/",
            {"username": "locked-user", "password": "correct-pass"},
            **request_kwargs,
        )
        self.assertEqual(still_locked.status_code, 429, still_locked.content)

    @override_settings(AXES_FAILURE_LIMIT=3)
    def test_forwarded_client_ip_is_stable_across_heroku_router_changes(self):
        client = APIClient()
        wrong = {"username": "locked-user", "password": "wrong-pass"}

        for router_ip in ("10.1.20.233", "10.1.38.76"):
            response = client.post(
                "/api/auth/login/",
                wrong,
                format="json",
                REMOTE_ADDR=router_ip,
                # Heroku appends the address it observed on the right. The
                # left value simulates an untrusted caller-supplied header.
                HTTP_X_FORWARDED_FOR="203.0.113.55, 198.51.100.10",
            )
            self.assertEqual(response.status_code, 401, response.content)

        locked = client.post(
            "/api/auth/login/",
            wrong,
            format="json",
            REMOTE_ADDR="10.1.51.6",
            HTTP_X_FORWARDED_FOR="203.0.113.55, 198.51.100.10",
        )
        self.assertEqual(locked.status_code, 429, locked.content)


class SystemAnnouncementTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="お知らせ対象店")
        self.other_store = Store.objects.create(name="別店舗")
        self.manager = User.objects.create_user(username="manager", password="manager-pass")
        UserProfile.objects.create(
            user=self.manager,
            store=self.store,
            role=UserProfile.Role.MANAGER,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.manager)

    def _announcement(self, title, audience=SystemAnnouncement.Audience.ALL, **kwargs):
        return SystemAnnouncement.objects.create(
            title=title,
            body=f"{title}本文",
            audience=audience,
            **kwargs,
        )

    def test_visibility_store_scope_and_read_receipts(self):
        global_notice = self._announcement("全体")
        operator_notice = self._announcement(
            "対象店舗の運営",
            audience=SystemAnnouncement.Audience.OPERATORS,
            target_path="/account/security",
        )
        operator_notice.target_stores.add(self.store)
        wrong_store = self._announcement(
            "別店舗",
            audience=SystemAnnouncement.Audience.OPERATORS,
        )
        wrong_store.target_stores.add(self.other_store)
        self._announcement("キャスト限定", audience=SystemAnnouncement.Audience.CASTS)
        self._announcement(
            "未来",
            published_at=timezone.now() + timedelta(days=1),
        )
        self._announcement("停止中", is_active=False)
        external_path = self._announcement("外部リンク不可", target_path="https://example.com")

        response = self.client.get("/api/auth/announcements/")

        self.assertEqual(response.status_code, 200, response.data)
        ids = {item["id"] for item in response.data["announcements"]}
        self.assertEqual(ids, {global_notice.id, operator_notice.id, external_path.id})
        serialized_external = next(
            item for item in response.data["announcements"] if item["id"] == external_path.id
        )
        self.assertEqual(serialized_external["target_path"], "")
        self.assertEqual(response.data["unread_count"], 3)

        mark_response = self.client.post(
            "/api/auth/announcements/",
            {"announcement_ids": [operator_notice.id, wrong_store.id]},
            format="json",
        )
        self.assertEqual(mark_response.status_code, 200, mark_response.data)
        self.assertEqual(mark_response.data["unread_count"], 2)
        self.assertTrue(
            SystemAnnouncementReadReceipt.objects.filter(
                announcement=operator_notice,
                user=self.manager,
            ).exists()
        )
        self.assertFalse(
            SystemAnnouncementReadReceipt.objects.filter(
                announcement=wrong_store,
                user=self.manager,
            ).exists()
        )
