from django.test import TestCase, override_settings

from core import test_sales_allocation as fixtures
from core.models import Option


@override_settings(SMS_DUMMY_MODE=True)
class CardOptionPreselectionTest(TestCase):
    setUp = fixtures.SalesAllocationTest.setUp

    def test_zero_options_selection_survives_later_options_and_completed_edit(self):
        self.order.payment_method = "CARD"
        self.order.options_price = 0
        self.order.total_price = 20000
        self.order.save()
        url = f"/api/orders/{self.order.pk}/correct-accounting/"
        def correct(**body):
            self.order.refresh_from_db()
            response = self.manager_client.post(url, {
                "reason": "OP支払い選択確認", "expected_updated_at": self.order.updated_at.isoformat(), **body,
            }, format="json")
            self.assertEqual(response.status_code, 200, response.data)
            return response.data
        result = correct(card_include_options=True)
        self.assertTrue(result["card_include_options"])
        self.assertTrue(self.manager_client.get(f"/api/orders/{self.order.pk}/").data["card_include_options"])
        option = Option.objects.create(store=self.store, name="検証OP", price=2000)
        result = correct(options=[option.pk])
        self.assertTrue(result["card_include_options"])
        self.assertEqual(result["total_price"], 22000)
        self.assertTrue(correct(options=[])["card_include_options"])
        self.assertTrue(correct(options=[option.pk])["card_include_options"])
        self.assertFalse(correct(payment_method="CASH")["card_include_options"])
        self.assertFalse(correct(payment_method="CARD")["card_include_options"])
