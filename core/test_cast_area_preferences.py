from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Cast, Store, UserProfile


User = get_user_model()


class CastAreaPreferencesTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="希望エリアテスト店")
        self.other_store = Store.objects.create(name="別店舗")
        self.cast = Cast.objects.create(store=self.store, name="希望キャスト")
        self.other_cast = Cast.objects.create(store=self.other_store, name="別店舗キャスト")
        self.manager = self.create_user("area_manager", UserProfile.Role.MANAGER)
        self.staff = self.create_user("area_staff", UserProfile.Role.STAFF)
        self.cast_user = self.create_user("area_cast", UserProfile.Role.CAST)

    def create_user(self, username, role):
        user = User.objects.create_user(username=username)
        UserProfile.objects.create(user=user, store=self.store, role=role)
        return user

    def client_as(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_manager_can_save_and_read_five_ranked_areas(self):
        response = self.client_as(self.manager).patch(
            f"/api/casts/{self.cast.id}/",
            {
                "preferred_area_1": "新宿",
                "preferred_area_2": "渋谷",
                "preferred_area_3": "池袋",
                "preferred_area_4": "五反田",
                "preferred_area_5": "上野",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.cast.refresh_from_db()
        self.assertEqual(self.cast.preferred_area_1, "新宿")
        self.assertEqual(self.cast.preferred_area_5, "上野")
        self.assertEqual(response.data["preferred_area_3"], "池袋")

    def test_rank_gaps_and_duplicate_areas_are_rejected(self):
        gap_response = self.client_as(self.manager).patch(
            f"/api/casts/{self.cast.id}/",
            {"preferred_area_1": "新宿", "preferred_area_3": "池袋"},
            format="json",
        )
        duplicate_response = self.client_as(self.manager).patch(
            f"/api/casts/{self.cast.id}/",
            {"preferred_area_1": "新宿", "preferred_area_2": " 新宿 "},
            format="json",
        )

        self.assertEqual(gap_response.status_code, 400, gap_response.data)
        self.assertEqual(duplicate_response.status_code, 400, duplicate_response.data)
        self.cast.refresh_from_db()
        self.assertEqual(self.cast.preferred_area_1, "")

    def test_only_manager_can_change_area_preferences(self):
        for user in (self.staff, self.cast_user):
            response = self.client_as(user).patch(
                f"/api/casts/{self.cast.id}/",
                {"preferred_area_1": "新宿"},
                format="json",
            )
            self.assertEqual(response.status_code, 403, response.data)

        self.cast.refresh_from_db()
        self.assertEqual(self.cast.preferred_area_1, "")

    def test_other_store_cast_cannot_be_updated(self):
        response = self.client_as(self.manager).patch(
            f"/api/casts/{self.other_cast.id}/",
            {"preferred_area_1": "新宿"},
            format="json",
        )

        self.assertEqual(response.status_code, 404, response.data)
        self.other_cast.refresh_from_db()
        self.assertEqual(self.other_cast.preferred_area_1, "")
