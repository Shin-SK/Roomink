from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Cast, DailySettlement, Store, StoreMembership, UserProfile


User = get_user_model()


class IdentityDeactivationTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="アカウント失効テスト店")
        self.manager = self.create_user("manager", UserProfile.Role.MANAGER)
        self.other_manager = self.create_user("other-manager", UserProfile.Role.MANAGER)
        self.staff = self.create_user("departing-staff", UserProfile.Role.STAFF)
        self.client = APIClient()
        self.client.force_authenticate(self.manager)

    def create_user(self, username, role):
        user = User.objects.create_user(username=username, password="test-pass-123")
        UserProfile.objects.create(user=user, store=self.store, role=role)
        return user

    def test_staff_removal_revokes_store_access_and_preserves_identity(self):
        profile = self.staff.profile
        settlement = DailySettlement.objects.create(
            store=self.store,
            date="2031-01-01",
            status=DailySettlement.Status.LOCKED,
            locked_by=self.staff,
        )

        response = self.client.delete(f"/api/staffs/{profile.pk}/")

        self.assertEqual(response.status_code, 204, response.data)
        self.staff.refresh_from_db()
        settlement.refresh_from_db()
        self.assertTrue(self.staff.is_active)
        self.assertEqual(settlement.locked_by, self.staff)
        self.assertTrue(UserProfile.objects.filter(user=self.staff).exists())
        self.assertFalse(StoreMembership.objects.filter(user=self.staff, store=self.store, is_active=True).exists())

        removed_client = APIClient()
        login = removed_client.post(
            "/api/auth/login/",
            {"username": "departing-staff", "password": "test-pass-123"},
            format="json",
        )
        self.assertEqual(login.status_code, 200, login.data)
        self.assertEqual(removed_client.get("/api/customers/").status_code, 403)
        self.assertEqual(removed_client.get("/api/auth/me/").data["role"], "unassigned")

    def test_last_active_manager_cannot_be_removed(self):
        response = self.client.delete(f"/api/staffs/{self.other_manager.profile.pk}/")
        self.assertEqual(response.status_code, 204, response.data)

        platform_admin = User.objects.create_superuser(
            username="platform-admin",
            email="platform-admin@example.com",
            password="test-pass-123",
        )
        platform_client = APIClient()
        platform_client.force_authenticate(platform_admin)
        session = platform_client.session
        session["platform_store_id"] = self.store.id
        session.save()

        response = platform_client.delete(f"/api/staffs/{self.manager.profile.pk}/")
        self.assertEqual(response.status_code, 400, response.data)
        self.manager.refresh_from_db()
        self.assertTrue(self.manager.is_active)

    def test_cast_removal_disables_linked_login(self):
        cast_user = self.create_user("departing-cast", UserProfile.Role.CAST)
        cast = Cast.objects.create(store=self.store, user=cast_user, name="退職キャスト")

        response = self.client.delete(f"/api/casts/{cast.pk}/")

        self.assertEqual(response.status_code, 204, response.data)
        cast_user.refresh_from_db()
        self.assertFalse(cast_user.is_active)
        self.assertFalse(Cast.objects.filter(pk=cast.pk).exists())
