from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Cast, Customer, Store, UserProfile


User = get_user_model()


class NumericUsernameLoginTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="認証テスト店舗")
        self.other_store = Store.objects.create(name="認証テスト別店舗")

        self.numeric_staff = self._create_operator(
            "123456", "numeric-staff-pass", UserProfile.Role.STAFF,
        )
        self.phone_like_manager = self._create_operator(
            "09012345678", "phone-like-manager-pass", UserProfile.Role.MANAGER,
        )
        self.international_numeric_manager = self._create_operator(
            "819012345678", "international-manager-pass", UserProfile.Role.MANAGER,
        )
        self.alphanumeric_manager = self._create_operator(
            "manager2", "alphanumeric-manager-pass", UserProfile.Role.MANAGER,
        )
        self.cast_user = self._create_operator(
            "cast01", "cast-pass", UserProfile.Role.CAST,
        )
        Cast.objects.create(store=self.store, user=self.cast_user, name="認証テストキャスト")

        self.customer_user = User.objects.create_user(
            username="customer_account",
            password="customer-pass",
        )
        self.customer = Customer.objects.create(
            store=self.store,
            user=self.customer_user,
            phone="090-1234-5678",
            display_name="認証テスト顧客",
        )

    def _create_operator(self, username, password, role):
        user = User.objects.create_user(username=username, password=password)
        UserProfile.objects.create(user=user, store=self.store, role=role)
        return user

    def _operator_login(self, username, password):
        client = APIClient()
        response = client.post(
            "/api/auth/login/",
            {"username": username, "password": password},
            format="json",
        )
        return client, response

    def test_numeric_only_staff_username_logs_in_as_username(self):
        client, response = self._operator_login("123456", "numeric-staff-pass")

        self.assertEqual(response.status_code, 200, response.data)
        me = client.get("/api/auth/me/")
        self.assertEqual(me.status_code, 200, me.data)
        self.assertEqual(me.data["username"], "123456")
        self.assertEqual(me.data["role"], UserProfile.Role.STAFF)

    def test_phone_like_manager_username_logs_in_as_username(self):
        client, response = self._operator_login(
            "09012345678", "phone-like-manager-pass",
        )

        self.assertEqual(response.status_code, 200, response.data)
        me = client.get("/api/auth/me/")
        self.assertEqual(me.data["username"], "09012345678")
        self.assertEqual(me.data["role"], UserProfile.Role.MANAGER)

    def test_numeric_username_is_not_rewritten_as_japanese_phone_number(self):
        client, response = self._operator_login(
            "819012345678", "international-manager-pass",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(client.get("/api/auth/me/").data["username"], "819012345678")

    def test_alphanumeric_manager_and_cast_login_regression(self):
        for username, password, role in (
            ("manager2", "alphanumeric-manager-pass", UserProfile.Role.MANAGER),
            ("cast01", "cast-pass", UserProfile.Role.CAST),
        ):
            with self.subTest(username=username):
                client, response = self._operator_login(username, password)
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(client.get("/api/auth/me/").data["role"], role)

    def test_same_string_uses_endpoint_context_without_cross_fallback(self):
        operator_client, operator_response = self._operator_login(
            "09012345678", "phone-like-manager-pass",
        )
        customer_client = APIClient()
        customer_response = customer_client.post(
            "/api/cu/login/",
            {"phone": "09012345678", "password": "customer-pass"},
            format="json",
        )

        self.assertEqual(operator_response.status_code, 200, operator_response.data)
        self.assertEqual(customer_response.status_code, 200, customer_response.data)
        self.assertEqual(
            operator_client.get("/api/auth/me/").data["username"],
            self.phone_like_manager.username,
        )
        self.assertEqual(
            customer_client.get("/api/auth/me/").data["username"],
            self.customer_user.username,
        )

        wrong_operator = APIClient().post(
            "/api/auth/login/",
            {"username": "09012345678", "password": "customer-pass"},
            format="json",
        )
        wrong_customer = APIClient().post(
            "/api/cu/login/",
            {"phone": "09012345678", "password": "phone-like-manager-pass"},
            format="json",
        )
        self.assertEqual(wrong_operator.status_code, 401)
        self.assertEqual(wrong_customer.status_code, 401)

    def test_customer_phone_login_failure_response_does_not_enumerate(self):
        wrong_password = APIClient().post(
            "/api/cu/login/",
            {"phone": "09012345678", "password": "wrong-pass"},
            format="json",
        )
        missing_phone = APIClient().post(
            "/api/cu/login/",
            {"phone": "09000000000", "password": "wrong-pass"},
            format="json",
        )

        self.assertEqual(wrong_password.status_code, 401)
        self.assertEqual(missing_phone.status_code, 401)
        self.assertEqual(wrong_password.json(), missing_phone.json())

    def test_customer_phone_login_rejects_multiple_distinct_users(self):
        other_user = User.objects.create_user(
            username="other_customer_account",
            password="customer-pass",
        )
        Customer.objects.create(
            store=self.other_store,
            user=other_user,
            phone="09012345678",
            display_name="別ユーザーの同一電話番号",
        )

        ambiguous = APIClient().post(
            "/api/cu/login/",
            {"phone": "09012345678", "password": "customer-pass"},
            format="json",
        )
        missing = APIClient().post(
            "/api/cu/login/",
            {"phone": "09000000000", "password": "customer-pass"},
            format="json",
        )

        self.assertEqual(ambiguous.status_code, 401)
        self.assertEqual(ambiguous.json(), missing.json())

    def test_login_does_not_grant_another_role_permissions(self):
        staff_client, staff_login = self._operator_login("123456", "numeric-staff-pass")
        customer_client = APIClient()
        customer_login = customer_client.post(
            "/api/cu/login/",
            {"phone": "09012345678", "password": "customer-pass"},
            format="json",
        )

        self.assertEqual(staff_login.status_code, 200)
        self.assertEqual(customer_login.status_code, 200)
        self.assertEqual(staff_client.get("/api/cu/mypage/").status_code, 403)
        self.assertEqual(customer_client.get("/api/orders/").status_code, 403)

        cast_client, cast_login = self._operator_login("cast01", "cast-pass")
        self.assertEqual(cast_login.status_code, 200)
        self.assertEqual(
            cast_client.get("/api/op/sales-dashboard/?range=today").status_code,
            403,
        )

    def test_logout_and_csrf_protection_remain_enabled(self):
        client = APIClient(enforce_csrf_checks=True)
        csrf_response = client.get("/api/auth/csrf/")
        csrf_token = csrf_response.cookies["csrftoken"].value
        login_response = client.post(
            "/api/auth/login/",
            {"username": "123456", "password": "numeric-staff-pass"},
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(login_response.status_code, 200, login_response.data)
        self.assertEqual(client.post("/api/auth/logout/", format="json").status_code, 403)
        refreshed_csrf_token = client.get("/api/auth/me/").cookies["csrftoken"].value
        logout_response = client.post(
            "/api/auth/logout/",
            format="json",
            HTTP_X_CSRFTOKEN=refreshed_csrf_token,
        )
        self.assertEqual(logout_response.status_code, 200, logout_response.data)
        self.assertEqual(client.get("/api/auth/me/").status_code, 403)
