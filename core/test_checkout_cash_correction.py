from datetime import datetime, timedelta
from unittest.mock import patch
from unittest import skipUnless
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase, override_settings
from django.db import connection, close_old_connections
from rest_framework.test import APIClient

from core import test_sales_allocation as fixtures
from core.models import CastDailyCheckout, CastCheckoutCashCorrection, DailySettlement, Order, Store, UserProfile, RoomCashMovement


@override_settings(SMS_DUMMY_MODE=True)
class CheckoutCashCorrectionTest(TestCase):
    setUp = fixtures.SalesAllocationTest.setUp

    def submit(self, amount=5000):
        with patch('core.views.timezone.now', return_value=datetime(2026, 10, 2, 20, tzinfo=ZoneInfo('Asia/Tokyo'))):
            response = self.cast_client.post('/api/cast/checkout/', {'room_cash_taken_amount': amount}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return CastDailyCheckout.objects.get(pk=response.data['id'])

    def review(self, checkout, **changes):
        return {'action': 'correct', 'expected_updated_at': checkout.updated_at.isoformat(), 'room_cash_taken_amount': 0, 'reason': '操作練習の入力で実際の受渡しなし', **changes}

    def cancel(self, checkout, **changes):
        return self.manager_client.post(f'/api/orders/{self.order.pk}/cancel/', {'expected_updated_at': self.order.updated_at.isoformat(), 'checkout_cash_review': self.review(checkout, **changes)}, format='json')

    def correct(self, checkout, **changes):
        return self.manager_client.patch(f'/api/cast-checkouts/{checkout.pk}/cash-receipt-correction/', self.review(checkout, **changes), format='json')

    @patch('core.views.notify_order_cancelled')
    def test_cancellation_and_practice_receipt_correction_are_atomic_and_audited(self, notify):
        checkout = self.submit()
        self.assertEqual(self.cancel(checkout).status_code, 200)
        checkout.refresh_from_db(); self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'CANCELLED')
        self.assertEqual((checkout.estimated_pay, checkout.room_cash_taken_amount, checkout.actual_take_home_amount), (0, 0, 0))
        audit = CastCheckoutCashCorrection.objects.get()
        self.assertEqual((audit.before['room_cash_taken_amount'], audit.after['room_cash_taken_amount']), (5000, 0))
        self.assertEqual(audit.order, self.order)
        self.assertTrue(audit.corrected_by_id)
        detail = self.manager_client.get(f'/api/cast-checkouts/{checkout.pk}/').data
        self.assertEqual(detail['carryover_closing_amount'], 0)
        self.assertEqual(detail['cash_corrections'][0]['reason'], audit.reason)
        self.assertEqual(self.cancel(checkout).status_code, 400)
        self.assertEqual(CastCheckoutCashCorrection.objects.count(), 1)
        notify.assert_called_once()

    @patch('core.views.notify_order_cancelled')
    def test_real_handover_is_kept_and_office_payments_and_returns_are_not_erased(self, notify):
        checkout = self.submit()
        checkout.office_cash_paid_amount = 1000; checkout.cash_returned_to_room_amount = 200
        checkout.save()
        self.assertEqual(self.cancel(checkout, action='keep').status_code, 200)
        checkout.refresh_from_db()
        self.assertEqual((checkout.room_cash_taken_amount, checkout.office_cash_paid_amount, checkout.cash_returned_to_room_amount), (5000, 1000, 200))
        self.assertFalse(CastCheckoutCashCorrection.objects.exists())
        self.assertEqual(self.correct(checkout).status_code, 200)
        checkout.refresh_from_db()
        self.assertEqual((checkout.room_cash_taken_amount, checkout.office_cash_paid_amount, checkout.cash_returned_to_room_amount), (0, 1000, 200))

    @patch('core.views.notify_order_cancelled')
    def test_other_reservations_same_day_are_kept_with_explicit_daily_handover(self, notify):
        other = Order.objects.get(pk=self.order.pk); other.pk = None
        other.start += timedelta(hours=2); other.end += timedelta(hours=2); other.save()
        checkout = self.submit(10000)
        self.assertEqual(self.cancel(checkout, room_cash_taken_amount=5000).status_code, 200)
        checkout.refresh_from_db(); other.refresh_from_db()
        self.assertEqual((checkout.done_count, checkout.total_sales, checkout.room_cash_taken_amount), (1, 24000, 5000))
        self.assertEqual(other.status, 'DONE')
        self.assertEqual(list(checkout.expense_snapshots.values_list('amount', flat=True)), [5000])

    @patch('core.views.notify_order_cancelled')
    def test_missing_confirmation_stale_checkout_and_invalid_input_leave_order_unchanged(self, notify):
        checkout = self.submit()
        response = self.manager_client.post(f'/api/orders/{self.order.pk}/cancel/', {'expected_updated_at': self.order.updated_at.isoformat()}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.cancel(checkout, expected_updated_at='2000-01-01T00:00:00Z').status_code, 409)
        for amount in (-1, 1.5, True, None, 'nan'):
            with self.subTest(amount=amount): self.assertEqual(self.cancel(checkout, room_cash_taken_amount=amount).status_code, 400)
        self.assertEqual(self.cancel(checkout, reason=' ').status_code, 400)
        self.order.refresh_from_db(); checkout.refresh_from_db()
        self.assertEqual(self.order.status, 'DONE')
        self.assertEqual(checkout.room_cash_taken_amount, 5000)
        self.assertFalse(CastCheckoutCashCorrection.objects.exists())
        notify.assert_not_called()

    def test_old_practice_correction_conflict_validation_and_restore(self):
        checkout = self.submit()
        self.assertEqual(self.correct(checkout, reason='').status_code, 400)
        self.assertEqual(self.correct(checkout).status_code, 200)
        self.assertEqual(self.correct(checkout).status_code, 409)
        checkout.refresh_from_db()
        self.assertEqual(self.correct(checkout, room_cash_taken_amount=5000, reason='訂正の取消：実受渡しを再確認').status_code, 200)
        self.assertEqual(CastCheckoutCashCorrection.objects.count(), 2)
        checkout.refresh_from_db()
        self.assertEqual(checkout.room_cash_taken_amount, 5000)

    def test_malformed_correction_and_returned_checkout(self):
        checkout = self.submit()
        url = f'/api/cast-checkouts/{checkout.pk}/cash-receipt-correction/'
        self.assertEqual(self.manager_client.patch(url, [], format='json').status_code, 400)
        checkout.status = 'RETURNED'; checkout.save()
        self.assertEqual(self.correct(checkout).status_code, 200)
        checkout.refresh_from_db(); self.assertEqual(checkout.status, 'RETURNED')

    @patch('core.views.notify_order_cancelled')
    def test_locked_day_blocks_cancellation_and_cash_correction(self, notify):
        checkout = self.submit()
        DailySettlement.objects.create(store=self.store, date=self.day, status='LOCKED')
        self.assertEqual(self.cancel(checkout).status_code, 400)
        self.assertEqual(self.correct(checkout).status_code, 400)
        checkout.refresh_from_db(); self.assertEqual(checkout.room_cash_taken_amount, 5000)
        notify.assert_not_called()


    @patch('core.views.notify_order_cancelled')
    def test_unauthorized_roles_and_other_store_cannot_correct(self, notify):
        checkout = self.submit()
        context = self.manager_client.get(f'/api/orders/{self.order.pk}/cancellation-checkout/')
        self.assertTrue(context.data['checkout']['can_correct'])
        staff = get_user_model().objects.create_user('cash-correction-staff')
        UserProfile.objects.create(user=staff, store=self.store, role='staff')
        foreign = get_user_model().objects.create_user('cash-correction-foreign')
        UserProfile.objects.create(user=foreign, store=Store.objects.create(name='他店舗'), role='manager')
        staff_client, foreign_client = APIClient(), APIClient()
        staff_client.force_authenticate(staff); foreign_client.force_authenticate(foreign)
        self.assertFalse(staff_client.get(f'/api/orders/{self.order.pk}/cancellation-checkout/').data['checkout']['can_correct'])
        for client, expected in ((self.cast_client, 403), (staff_client, 403), (foreign_client, 404), (APIClient(), 403)):
            self.assertEqual(client.patch(f'/api/cast-checkouts/{checkout.pk}/cash-receipt-correction/', self.review(checkout), format='json').status_code, expected)
        self.assertEqual(foreign_client.get(f'/api/orders/{self.order.pk}/cancellation-checkout/').status_code, 404)
        self.assertEqual(staff_client.post(f'/api/orders/{self.order.pk}/cancel/', {'expected_updated_at': self.order.updated_at.isoformat(), 'checkout_cash_review': self.review(checkout)}, format='json').status_code, 403)
        self.order.refresh_from_db(); self.assertEqual(self.order.status, 'DONE')

    @patch('core.views.notify_order_cancelled')
    def test_audit_failure_rolls_back_order_checkout_and_cash_movement(self, notify):
        checkout = self.submit(); count = RoomCashMovement.objects.count()
        with patch('core.models.CastCheckoutCashCorrection.objects.create', side_effect=RuntimeError('audit storage unavailable')):
            with self.assertRaises(RuntimeError): self.cancel(checkout)
        self.order.refresh_from_db(); checkout.refresh_from_db()
        self.assertEqual((self.order.status, checkout.room_cash_taken_amount), ('DONE', 5000))
        self.assertEqual(RoomCashMovement.objects.count(), count)
        notify.assert_not_called()


@skipUnless(connection.vendor == 'postgresql', 'requires PostgreSQL row locks')
@override_settings(SMS_DUMMY_MODE=True)
class CheckoutCashCorrectionConcurrencyTest(TransactionTestCase):
    setUp = fixtures.SalesAllocationTest.setUp
    submit = CheckoutCashCorrectionTest.submit

    def test_parallel_receipt_edits_only_apply_one_and_leave_one_audit(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        checkout = self.submit()
        user = self.manager_client.handler._force_user
        barrier = Barrier(2)
        def correct(amount):
            close_old_connections()
            try:
                client = APIClient(); client.force_authenticate(user)
                barrier.wait(timeout=10)
                response = client.patch(f'/api/cast-checkouts/{checkout.pk}/cash-receipt-correction/', {
                    'expected_updated_at': checkout.updated_at.isoformat(), 'room_cash_taken_amount': amount,
                    'reason': '並行訂正の確認',
                }, format='json')
                return response.status_code
            finally: close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            codes = list(pool.map(correct, [0, 1000]))
        self.assertEqual(sorted(codes), [200, 409])
        self.assertEqual(CastCheckoutCashCorrection.objects.count(), 1)
