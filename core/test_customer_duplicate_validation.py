from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Customer, Store, UserProfile


User = get_user_model()


class CustomerDuplicateValidationTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="顧客重複テスト店舗")
        self.manager = User.objects.create_user("customer-duplicate-manager")
        UserProfile.objects.create(
            user=self.manager,
            store=self.store,
            role=UserProfile.Role.MANAGER,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.manager)

    def test_existing_phone_returns_field_validation_error_instead_of_server_error(self):
        Customer.objects.create(
            store=self.store,
            phone="09012345678",
            display_name="既存顧客",
        )

        response = self.client.post(
            "/api/customers/",
            {"phone": "090-1234-5678", "display_name": "新規顧客"},
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(
            response.data["phone"],
            ["この電話番号は既に登録されています。既存顧客を選択してください。"],
        )
        self.assertEqual(Customer.objects.filter(store=self.store).count(), 1)

    def test_same_phone_can_be_created_for_a_different_store(self):
        Customer.objects.create(store=self.store, phone="09012345678")
        other_store = Store.objects.create(name="別店舗")
        other_manager = User.objects.create_user("customer-duplicate-other-manager")
        UserProfile.objects.create(
            user=other_manager,
            store=other_store,
            role=UserProfile.Role.MANAGER,
        )
        other_client = APIClient()
        other_client.force_authenticate(other_manager)

        response = other_client.post(
            "/api/customers/",
            {"phone": "09012345678", "display_name": "別店舗顧客"},
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Customer.objects.filter(store=other_store).count(), 1)
