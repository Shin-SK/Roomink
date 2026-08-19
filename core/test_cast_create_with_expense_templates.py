from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import (
    Cast,
    CastExpenseTemplate,
    CastExpenseTemplateHistory,
    Store,
    UserProfile,
)


User = get_user_model()


class CastCreateWithExpenseTemplatesTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="キャスト同時登録テスト店")
        self.manager = User.objects.create_user("cast_create_manager")
        UserProfile.objects.create(
            user=self.manager,
            store=self.store,
            role=UserProfile.Role.MANAGER,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.manager)

    def test_manager_can_create_cast_and_multiple_expense_templates_together(self):
        response = self.client.post(
            "/api/casts/",
            {
                "name": "同時登録キャスト",
                "expense_templates": [
                    {"name": "雑費", "amount": 1000, "memo": "日額"},
                    {"name": "備品代", "amount": 500, "memo": ""},
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        cast = Cast.objects.get(name="同時登録キャスト")
        templates = list(
            CastExpenseTemplate.objects.filter(cast=cast).order_by("id")
        )
        self.assertEqual([template.name for template in templates], ["雑費", "備品代"])
        self.assertEqual([template.amount for template in templates], [1000, 500])
        self.assertTrue(all(template.store_id == self.store.id for template in templates))

        histories = list(
            CastExpenseTemplateHistory.objects.filter(cast=cast).order_by("id")
        )
        self.assertEqual(len(histories), 2)
        self.assertTrue(
            all(
                history.action == CastExpenseTemplateHistory.Action.CREATE
                and history.edited_by_id == self.manager.id
                for history in histories
            )
        )

    def test_invalid_expense_template_rolls_back_cast_creation(self):
        response = self.client.post(
            "/api/casts/",
            {
                "name": "ロールバック対象キャスト",
                "expense_templates": [
                    {"name": "不正雑費", "amount": -1, "memo": ""},
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(Cast.objects.filter(name="ロールバック対象キャスト").exists())
        self.assertFalse(CastExpenseTemplate.objects.exists())
        self.assertFalse(CastExpenseTemplateHistory.objects.exists())

    def test_existing_cast_creation_without_expenses_is_unchanged(self):
        response = self.client.post(
            "/api/casts/",
            {"name": "雑費なしキャスト"},
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        cast = Cast.objects.get(name="雑費なしキャスト")
        self.assertFalse(CastExpenseTemplate.objects.filter(cast=cast).exists())
