from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Area, Cast, CastAreaPreference, Store, UserProfile


User = get_user_model()


class CastAreaPreferencesTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="希望エリアテスト店")
        self.other_store = Store.objects.create(name="別店舗")
        self.areas = [Area.objects.create(store=self.store, name=name) for name in ("新宿", "渋谷", "池袋")]
        self.other_area = Area.objects.create(store=self.other_store, name="他店舗エリア")
        self.cast = Cast.objects.create(store=self.store, name="希望キャスト")
        self.other_cast = Cast.objects.create(store=self.other_store, name="別店舗キャスト")
        self.manager = self.create_user("area_manager", UserProfile.Role.MANAGER)
        self.staff = self.create_user("area_staff", UserProfile.Role.STAFF)
        self.cast_user = self.create_user("area_cast", UserProfile.Role.CAST)

    def create_user(self, username, role):
        user = User.objects.create_user(username)
        UserProfile.objects.create(user=user, store=self.store, role=role)
        return user

    def client_as(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_manager_can_save_ranked_area_master_ids(self):
        response = self.client_as(self.manager).patch(
            f"/api/casts/{self.cast.id}/",
            {"preferred_area_ids": [area.id for area in self.areas]}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            list(CastAreaPreference.objects.filter(cast=self.cast).values_list("area_id", flat=True)),
            [area.id for area in self.areas],
        )
        self.assertEqual([item["name"] for item in response.data["preferred_areas"]], ["新宿", "渋谷", "池袋"])

    def test_duplicate_or_other_store_area_is_rejected(self):
        duplicate = self.client_as(self.manager).patch(
            f"/api/casts/{self.cast.id}/",
            {"preferred_area_ids": [self.areas[0].id, self.areas[0].id]}, format="json",
        )
        foreign = self.client_as(self.manager).patch(
            f"/api/casts/{self.cast.id}/",
            {"preferred_area_ids": [self.other_area.id]}, format="json",
        )
        self.assertEqual(duplicate.status_code, 400, duplicate.data)
        self.assertEqual(foreign.status_code, 400, foreign.data)

    def test_only_manager_can_change_area_preferences(self):
        for user in (self.staff, self.cast_user):
            response = self.client_as(user).patch(
                f"/api/casts/{self.cast.id}/",
                {"preferred_area_ids": [self.areas[0].id]}, format="json",
            )
            self.assertEqual(response.status_code, 403, response.data)

    def test_other_store_cast_cannot_be_updated(self):
        response = self.client_as(self.manager).patch(
            f"/api/casts/{self.other_cast.id}/",
            {"preferred_area_ids": [self.areas[0].id]}, format="json",
        )
        self.assertEqual(response.status_code, 404, response.data)
