from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Cast, Store, UserProfile


User = get_user_model()


class CastAccountProvisioningTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="アカウント発行テスト店")
        self.other_store = Store.objects.create(name="別店舗")
        self.manager = self.create_operator("account_manager", self.store, UserProfile.Role.MANAGER)
        self.staff = self.create_operator("account_staff", self.store, UserProfile.Role.STAFF)
        self.cast = Cast.objects.create(store=self.store, name="未発行キャスト")
        self.other_cast = Cast.objects.create(store=self.other_store, name="別店舗キャスト")

    def create_operator(self, username, store, role):
        user = User.objects.create_user(username=username, password="operator-pass")
        UserProfile.objects.create(user=user, store=store, role=role)
        return user

    def client_as(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_manager_can_issue_login_for_existing_cast(self):
        response = self.client_as(self.manager).post(
            f"/api/casts/{self.cast.pk}/provision-account/",
            {"username": "rs_cast_001", "password": "temporary-pass-123"},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.cast.refresh_from_db()
        self.assertIsNotNone(self.cast.user_id)
        self.assertEqual(self.cast.user.username, "rs_cast_001")
        self.assertTrue(self.cast.user.check_password("temporary-pass-123"))
        self.assertEqual(self.cast.user.profile.store, self.store)
        self.assertEqual(self.cast.user.profile.role, UserProfile.Role.CAST)
        self.assertTrue(response.data["account_enabled"])
        self.assertEqual(response.data["account_username"], "rs_cast_001")

    def test_manager_can_reset_existing_cast_temporary_password(self):
        cast_user = self.create_operator("existing_cast", self.store, UserProfile.Role.CAST)
        self.cast.user = cast_user
        self.cast.save(update_fields=["user"])

        response = self.client_as(self.manager).post(
            f"/api/casts/{self.cast.pk}/provision-account/",
            {"username": "existing_cast", "password": "new-temporary-pass-123"},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        cast_user.refresh_from_db()
        self.assertTrue(cast_user.check_password("new-temporary-pass-123"))

    def test_staff_cannot_issue_cast_account(self):
        response = self.client_as(self.staff).post(
            f"/api/casts/{self.cast.pk}/provision-account/",
            {"username": "blocked_cast", "password": "temporary-pass-123"},
            format="json",
        )

        self.assertEqual(response.status_code, 403, response.data)
        self.cast.refresh_from_db()
        self.assertIsNone(self.cast.user_id)

    def test_manager_cannot_issue_account_for_other_store_cast(self):
        response = self.client_as(self.manager).post(
            f"/api/casts/{self.other_cast.pk}/provision-account/",
            {"username": "other_store_cast", "password": "temporary-pass-123"},
            format="json",
        )

        self.assertEqual(response.status_code, 404, response.data)
        self.other_cast.refresh_from_db()
        self.assertIsNone(self.other_cast.user_id)

    def test_existing_account_username_cannot_be_silently_changed(self):
        cast_user = self.create_operator("fixed_cast_username", self.store, UserProfile.Role.CAST)
        self.cast.user = cast_user
        self.cast.save(update_fields=["user"])

        response = self.client_as(self.manager).post(
            f"/api/casts/{self.cast.pk}/provision-account/",
            {"username": "different_username", "password": "temporary-pass-123"},
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.data)
        cast_user.refresh_from_db()
        self.assertEqual(cast_user.username, "fixed_cast_username")
