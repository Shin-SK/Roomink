from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core import test_sales_allocation as fixtures
from core.models import CastDailyCheckout, DailySettlement, OrderAccountingCorrection


@override_settings(SMS_DUMMY_MODE=True)
class CompletedCancellationTest(TestCase):
    setUp = fixtures.SalesAllocationTest.setUp

    def cancel(self, **body):
        return self.manager_client.post(f"/api/orders/{self.order.pk}/cancel/", {
            "expected_updated_at": self.order.updated_at.isoformat(), **body,
        }, format="json")

    @patch("core.views.notify_order_cancelled")
    def test_completed_cancel_once_and_audit(self, notify):
        self.assertEqual(self.cancel().status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "CANCELLED")
        self.assertIsNotNone(self.order.cancelled_by)
        self.assertEqual(OrderAccountingCorrection.objects.get().before, {"status": "DONE"})
        self.assertEqual(self.cancel().status_code, 400)
        notify.assert_called_once()

    @patch("core.views.timezone.now", return_value=datetime(2026, 10, 2, 20, tzinfo=ZoneInfo("Asia/Tokyo")))
    @patch("core.views.notify_order_cancelled")
    def test_submitted_checkout_updates_and_keeps_actual_cash(self, notify, now):
        response = self.cast_client.post("/api/cast/checkout/", {"room_cash_taken_amount": 5000}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.cancel(checkout_cash_review={"action": "keep", "expected_updated_at": response.data["updated_at"]}).status_code, 200)
        checkout = CastDailyCheckout.objects.get()
        self.assertEqual((checkout.done_count, checkout.total_sales, checkout.estimated_pay), (0, 0, 0))
        self.assertEqual(checkout.room_cash_taken_amount, 5000)
        self.assertEqual(list(checkout.expense_snapshots.values_list("amount", flat=True)), [0])
        self.assertEqual(OrderAccountingCorrection.objects.get().before["checkout_fixed_expenses"][0]["amount"], 5000)
        result = self.cast_client.get("/api/cast/checkout/?date=2026-10-02")
        self.assertEqual(result.data["fixed_expense_total"], 0)

    @patch("core.views.notify_order_cancelled")
    def test_lock_stale_and_permissions(self, notify):
        self.assertEqual(self.cancel(expected_updated_at="2000-01-01T00:00:00Z").status_code, 409)
        self.assertEqual(self.cast_client.post(f"/api/orders/{self.order.pk}/cancel/").status_code, 403)
        self.assertEqual(APIClient().post(f"/api/orders/{self.order.pk}/cancel/").status_code, 403)
        DailySettlement.objects.create(store=self.store, date=self.day, status="LOCKED")
        self.assertEqual(self.cancel().status_code, 400)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "DONE")
        notify.assert_not_called()

    @patch("core.views.notify_order_cancelled")
    def test_foreign_store_and_stale_checkout_are_rejected(self, notify):
        from django.contrib.auth import get_user_model
        from core.models import Store, UserProfile
        user = get_user_model().objects.create_user("foreign-cancel-manager")
        UserProfile.objects.create(user=user, store=Store.objects.create(name="別店舗"), role="manager")
        client = APIClient()
        client.force_authenticate(user)
        self.assertEqual(client.post(f"/api/orders/{self.order.pk}/cancel/").status_code, 404)
        CastDailyCheckout.objects.create(store=self.store, cast=self.cast, date=self.day, total_sales=0)
        self.assertEqual(self.cancel().status_code, 400)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "DONE")
        self.assertFalse(OrderAccountingCorrection.objects.exists())
        notify.assert_not_called()

    @patch("core.views.notify_order_cancelled")
    def test_cast_completion_can_then_be_cancelled_by_store(self, notify):
        self.order.status = "IN_PROGRESS"
        self.order.save()
        response = self.cast_client.post(f"/api/cast/orders/{self.order.pk}/complete/")
        self.assertEqual(response.status_code, 200, response.data)
        self.order.refresh_from_db()
        self.assertEqual(self.cancel().status_code, 200)
