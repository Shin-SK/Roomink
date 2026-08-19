from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Store, UserProfile


User = get_user_model()


class StaffOptionalEmailTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="スタッフ任意メールテスト店")
        self.manager = User.objects.create_user("staff_email_manager")
        UserProfile.objects.create(
            user=self.manager,
            store=self.store,
            role=UserProfile.Role.MANAGER,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.manager)

    def test_manager_can_create_staff_with_blank_email(self):
        response = self.client.post(
            "/api/staffs/",
            {
                "username": "blank_email_staff",
                "password": "test-pass-123",
                "email": "",
                "role": UserProfile.Role.STAFF,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["email"], "")
        self.assertEqual(User.objects.get(username="blank_email_staff").email, "")

    def test_manager_can_clear_existing_staff_email(self):
        staff_user = User.objects.create_user(
            "clear_email_staff",
            email="before@example.com",
        )
        profile = UserProfile.objects.create(
            user=staff_user,
            store=self.store,
            role=UserProfile.Role.STAFF,
        )

        response = self.client.patch(
            f"/api/staffs/{profile.pk}/",
            {"email": ""},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        staff_user.refresh_from_db()
        self.assertEqual(staff_user.email, "")
