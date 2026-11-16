import uuid
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core import test_sales_allocation
from core.models import CastDailyCheckout, DailySettlement, EnvelopeSubmission, Store, UserProfile


@patch('django.utils.timezone.now', return_value=datetime(2026, 10, 3, 20, tzinfo=ZoneInfo('Asia/Tokyo')))
class ManagerCheckoutTests(TestCase):
    setUp = test_sales_allocation.SalesAllocationTest.setUp
    url = '/api/cast-checkouts/register-by-store/'

    def row(self):
        response = self.manager_client.get('/api/op/daily-settlement/', {'date': str(self.day)})
        self.assertEqual(response.status_code, 200, response.data)
        return response.data['rows'][0]

    def payload(self, **changes):
        return {'cast': self.cast.pk, 'date': str(self.day), 'room_cash_taken_amount': 8000,
                'reason': '本人と封筒の金額を確認', 'request_id': str(uuid.uuid4()),
                'source_revision': self.row()['settlement_source_revision'], **changes}

    def test_store_registration_carries_balance_and_allows_envelope_receipt(self, _):
        before = self.row()
        self.assertEqual(before['remaining_receivable_amount'], 9000)
        self.assertFalse(before['cash_handover_recorded'])
        body = self.payload()
        response = self.manager_client.post(self.url, body, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        checkout = CastDailyCheckout.objects.get(cast=self.cast, date=self.day)
        self.assertEqual(checkout.registration_source, 'STORE')
        self.assertEqual(checkout.registered_by_id, self.manager_client.handler._force_user.pk)
        self.assertEqual(checkout.checklist_json, {})
        self.assertEqual(response.data['carryover_closing_amount'], 1000)
        self.assertEqual(EnvelopeSubmission.objects.get(checkout=checkout).deposit_amount, 16000)
        row = self.row()
        self.assertTrue(row['cash_handover_recorded'])
        self.assertEqual(row['remaining_receivable_amount'], 1000)
        receipts = self.manager_client.get('/api/op/envelope-receipts/', {'date': str(self.day)}).data['rows']
        self.assertTrue(receipts[0]['can_receive'])
        # Network retry is one registration, not another handover.
        retry = self.manager_client.post(self.url, body, format='json')
        self.assertEqual(retry.status_code, 200, retry.data)
        self.assertEqual(EnvelopeSubmission.objects.filter(checkout=checkout).count(), 1)
        changed = self.manager_client.post(self.url, {**body, 'room_cash_taken_amount': 7000}, format='json')
        self.assertEqual(changed.status_code, 409)
        # A later cast submission must not overwrite the store's real record.
        cast = self.cast_client.post('/api/cast/checkout/', {'date': str(self.day), 'room_cash_taken_amount': 0}, format='json')
        self.assertEqual(cast.status_code, 400)
        self.assertEqual(self.cast_client.get('/api/cast/checkout/', {'date': str(self.day)}).data['checkout']['registration_source'], 'STORE')
        # Confirmed past balance is carried into the next day's calculation.
        next_day = self.cast_client.get('/api/cast/checkout/', {'date': '2026-10-03'}).data
        self.assertEqual(next_day['carryover_opening_amount'], 1000)

    def test_stale_sales_and_existing_submission_cannot_be_overwritten(self, _):
        body = self.payload()
        self.order.options_price = 5000
        self.order.save()
        self.assertEqual(self.manager_client.post(self.url, body, format='json').status_code, 409)
        body = self.payload()
        self.assertEqual(self.cast_client.post('/api/cast/checkout/', {'date': str(self.day), 'room_cash_taken_amount': 8000}, format='json').status_code, 201)
        self.assertEqual(self.manager_client.post(self.url, body, format='json').status_code, 409)
        self.assertEqual(CastDailyCheckout.objects.get(cast=self.cast).room_cash_taken_amount, 8000)

    def test_missing_amount_invalid_money_and_reason_do_not_create_checkout(self, _):
        for value in [None, '', True, -1, 1.5, '1.5', 100000, 2147483648]:
            response = self.manager_client.post(self.url, self.payload(room_cash_taken_amount=value), format='json')
            self.assertEqual(response.status_code, 400, (value, response.data))
        for reason in ['', ' ', 4, 'x' * 501]:
            self.assertEqual(self.manager_client.post(self.url, self.payload(reason=reason), format='json').status_code, 400)
        self.assertFalse(CastDailyCheckout.objects.exists())
        self.assertEqual(self.manager_client.post(self.url, self.payload(room_cash_taken_amount=0), format='json').status_code, 201)

    def test_permissions_tenants_future_day_and_day_lock(self, _):
        body = self.payload()
        self.assertEqual(APIClient().post(self.url, body, format='json').status_code, 403)
        self.assertEqual(self.cast_client.post(self.url, body, format='json').status_code, 403)
        other_store = Store.objects.create(name='別店舗')
        for role in ['staff', 'manager']:
            user = get_user_model().objects.create_user('registration-' + role)
            UserProfile.objects.create(user=user, store=other_store if role == 'manager' else self.store, role=role)
            client = APIClient(); client.force_authenticate(user)
            self.assertIn(client.post(self.url, body, format='json').status_code, [403, 404])
        self.assertEqual(self.manager_client.post(self.url, {**body, 'date': '2026-10-04'}, format='json').status_code, 400)
        DailySettlement.objects.create(store=self.store, date=self.day, status='LOCKED')
        self.assertEqual(self.manager_client.post(self.url, body, format='json').status_code, 400)
        self.assertFalse(CastDailyCheckout.objects.exists())

    def test_pending_days_are_not_silently_treated_as_zero(self, _):
        data = self.cast_client.get('/api/cast/checkout/', {'date': '2026-10-03'}).data
        self.assertEqual(data['carryover_opening_amount'], 0)
        self.assertEqual(data['unrecorded_prior_dates'], ['2026-10-02'])
        response = self.manager_client.get('/api/op/daily-settlement/', {'date': str(self.day)})
        self.assertEqual(response.data['rows'][0]['cash_settlement_amount'], 15000)
        # No actual payment is inferred from the current day's estimate.
        self.assertEqual(response.data['rows'][0]['room_cash_taken_amount'], None)

    def test_audit_failure_rolls_back_checkout_envelope_and_handover(self, _):
        body = self.payload()
        with patch('core.models.CastCheckoutRegistration.objects.create', side_effect=RuntimeError('audit failed')):
            with self.assertRaises(RuntimeError):
                self.manager_client.post(self.url, body, format='json')
        self.assertFalse(CastDailyCheckout.objects.exists())
        self.assertFalse(EnvelopeSubmission.objects.exists())

    def test_daily_display_and_csv_include_carryover_without_changing_daily_amount(self, _):
        from core.models import CastCheckoutExpenseSnapshot
        past = CastDailyCheckout.objects.create(store=self.store, cast=self.cast, date=self.day - timedelta(days=1), estimated_pay=2000)
        CastCheckoutExpenseSnapshot.objects.create(checkout=past, name='雑費', amount=500)
        row = self.row()
        self.assertEqual(row['carryover_opening_amount'], 1500)
        self.assertEqual(row['receivable_amount'], 10500)
        self.assertEqual(row['cash_settlement_amount'], 15000)
        csv = self.manager_client.get('/api/op/daily-settlement/export/', {'date': str(self.day)}).content.decode('utf-8-sig')
        self.assertIn('前回までの未受取', csv)
        self.assertIn('10500', csv)

    def test_returned_store_registration_preserves_office_payments_and_audit(self, _):
        first = self.manager_client.post(self.url, self.payload(), format='json')
        checkout = CastDailyCheckout.objects.get(pk=first.data['id'])
        checkout.status = 'RETURNED'
        checkout.office_cash_paid_amount = 300
        checkout.cash_returned_to_room_amount = 100
        checkout.save()
        body = self.payload(room_cash_taken_amount=7000)
        second = self.manager_client.post(self.url, body, format='json')
        self.assertEqual(second.status_code, 201, second.data)
        checkout.refresh_from_db()
        self.assertEqual(checkout.office_cash_paid_amount, 300)
        self.assertEqual(checkout.cash_returned_to_room_amount, 100)
        self.assertEqual(checkout.registrations.count(), 2)
        self.assertEqual(checkout.envelope_submissions.count(), 2)
        self.assertEqual(second.data['carryover_closing_amount'], 1700)

    def test_submitted_snapshot_is_used_even_after_rate_change(self, _):
        self.assertEqual(self.manager_client.post(self.url, self.payload(), format='json').status_code, 201)
        self.cast.course_back_rate = 30
        self.cast.save()
        row = self.row()
        self.assertEqual(row['settlement_compensation_amount'], 9000)
        self.assertEqual(row['remaining_receivable_amount'], 1000)

    def test_sale_without_shift_remains_available_for_store_registration(self, _):
        from core.models import ShiftAssignment
        ShiftAssignment.objects.filter(cast=self.cast).delete()
        self.assertTrue(self.row()['can_register_by_store'])
        self.assertEqual(self.manager_client.post(self.url, self.payload(), format='json').status_code, 201)

    def test_locked_snapshot_preserves_balance_and_cannot_register(self, _):
        before = self.row()
        response = self.manager_client.post('/api/op/daily-settlement/lock/', {'date': str(self.day)}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.row()['remaining_receivable_amount'], before['remaining_receivable_amount'])
        self.assertEqual(self.manager_client.post(self.url, self.payload(), format='json').status_code, 400)

    def test_cast_resubmission_retains_store_recorded_office_payment(self, _):
        response = self.manager_client.post(self.url, self.payload(), format='json')
        checkout = CastDailyCheckout.objects.get(pk=response.data['id'])
        checkout.status = 'RETURNED'; checkout.office_cash_paid_amount = 500
        checkout.cash_returned_to_room_amount = 100; checkout.save()
        bad = self.cast_client.post('/api/cast/checkout/', {'date': str(self.day), 'room_cash_taken_amount': 9000}, format='json')
        self.assertEqual(bad.status_code, 400)
        resubmit = self.cast_client.post('/api/cast/checkout/', {'date': str(self.day), 'room_cash_taken_amount': 8000}, format='json')
        self.assertEqual(resubmit.status_code, 201, resubmit.data)
        self.assertEqual(resubmit.data['office_cash_paid_amount'], 500)
        self.assertEqual(resubmit.data['cash_returned_to_room_amount'], 100)
        self.assertEqual(resubmit.data['carryover_closing_amount'], 500)

    def test_card_shortage_and_later_cash_day_share_one_balance(self, _):
        from core.models import CastCheckoutExpenseSnapshot
        past = CastDailyCheckout.objects.create(store=self.store, cast=self.cast, date=self.day - timedelta(days=1), estimated_pay=10000)
        CastCheckoutExpenseSnapshot.objects.create(checkout=past, name='雑費', amount=1000)
        self.fixed.amount = 1000; self.fixed.save()
        self.order.options_price = 0; self.order.total_price = 20000; self.order.save()
        row = self.row()
        self.assertEqual(row['cash_settlement_amount'], 7000)
        self.assertEqual(row['carryover_opening_amount'], 9000)
        self.assertEqual(row['receivable_amount'], 22000)
        response = self.manager_client.post(self.url, self.payload(room_cash_taken_amount=20000), format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.row()['remaining_receivable_amount'], 2000)

    def test_excess_deposit_is_unreceived_pay_plus_existing_balance(self, _):
        CastDailyCheckout.objects.create(store=self.store, cast=self.cast, date=self.day - timedelta(days=1), estimated_pay=500)
        self.cast.course_back_rate = 50; self.cast.save()
        self.fixed.amount = 1000; self.fixed.save()
        self.order.course_price = 46000; self.order.options_price = 0
        self.order.total_price = 45000; self.order.save()
        response = self.manager_client.post(self.url, self.payload(room_cash_taken_amount=15000), format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['carryover_closing_amount'], 7500)
        self.assertEqual(EnvelopeSubmission.objects.get(checkout_id=response.data['id']).deposit_amount, 30000)


from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from django.db import connection, close_old_connections
from django.test import TransactionTestCase


@skipUnless(connection.vendor == 'postgresql', 'Row locking requires PostgreSQL')
class ManagerCheckoutConcurrencyTests(TransactionTestCase):
    def setUp(self):
        from django.db.migrations.executor import MigrationExecutor
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        test_sales_allocation.SalesAllocationTest.setUp(self)

    def race(self, cast_second=False):
        row = self.manager_client.get('/api/op/daily-settlement/', {'date': str(self.day)}).data['rows'][0]
        body = {'cast': self.cast.pk, 'date': str(self.day), 'room_cash_taken_amount': 8000,
                'reason': '受取確認', 'source_revision': row['settlement_source_revision']}
        barrier = Barrier(2)
        manager_id = self.manager_client.handler._force_user.pk
        cast_user_id = self.cast.user_id

        def run(second):
            close_old_connections()
            try:
                client = APIClient()
                user = get_user_model().objects.get(pk=cast_user_id if second and cast_second else manager_id)
                client.force_authenticate(user)
                barrier.wait(timeout=10)
                if second and cast_second:
                    return client.post('/api/cast/checkout/', {'date': str(self.day), 'room_cash_taken_amount': 7000}, format='json').status_code
                return client.post('/api/cast-checkouts/register-by-store/', {**body, 'request_id': str(uuid.uuid4())}, format='json').status_code
            finally:
                close_old_connections()

        with patch('django.utils.timezone.now', return_value=datetime(2026, 10, 3, 20, tzinfo=ZoneInfo('Asia/Tokyo'))):
            with ThreadPoolExecutor(max_workers=2) as pool:
                statuses = list(pool.map(run, [False, True]))
        self.assertEqual(statuses.count(201), 1, statuses)
        self.assertTrue(any(code in (400, 409) for code in statuses), statuses)
        self.assertEqual(CastDailyCheckout.objects.filter(cast=self.cast).count(), 1)
        self.assertEqual(EnvelopeSubmission.objects.count(), 1)

    def test_two_store_operators_register_once(self):
        self.race()

    def test_cast_and_store_cannot_overwrite_each_other(self):
        self.race(cast_second=True)
