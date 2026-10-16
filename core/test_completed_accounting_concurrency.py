from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from core import test_sales_allocation as fixtures
from core.models import Discount, OrderAccountingCorrection


@skipUnless(connection.vendor == "postgresql", "PostgreSQL row locks are required")
class AccountingCorrectionConcurrencyTest(TransactionTestCase):
    setUp = fixtures.SalesAllocationTest.setUp

    def test_simultaneous_corrections_have_one_winner_and_one_audit(self):
        discount = Discount.objects.create(store=self.store, name="割引", value=2000)
        timestamp = self.order.updated_at.isoformat()
        actor = self.manager_client.handler._force_user
        barrier = Barrier(2)

        def correct():
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(actor)
                barrier.wait(timeout=10)
                return client.post(f"/api/orders/{self.order.pk}/correct-accounting/", {
                    "reason": "同時訂正の検証", "expected_updated_at": timestamp, "discount": discount.pk,
                }, format="json").status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            attempts = [pool.submit(correct) for _ in range(2)]
            self.assertEqual(sorted(attempt.result(timeout=30) for attempt in attempts), [200, 409])
        self.assertEqual(OrderAccountingCorrection.objects.count(), 1)
        self.order.refresh_from_db()
        self.assertEqual(self.order.total_price, 22000)
