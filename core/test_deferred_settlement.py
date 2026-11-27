import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.test_sales_allocation import SalesAllocationTest
from core.models import (Store, UserProfile, CastDailyCheckout, CastAccountingConfirmation,
    CastAccountingConfirmationEvent, EnvelopeSubmission, RoomCashMovement, DailySettlement)


class DeferredSettlementTests(TestCase):
    url = '/api/op/cast-accounting/'

    def setUp(self):
        SalesAllocationTest.setUp(self)
        self.store.deferred_settlement_from = self.day
        self.store.save(update_fields=['deferred_settlement_from'])
        from core.models import ShiftAssignment
        for offset in (1, 2):
            ShiftAssignment.objects.create(store=self.store, cast=self.cast,
                date=self.day + timedelta(days=offset), room=self.order.room,
                start_time='17:00', end_time='23:00')

    def payload(self, **changes):
        return {'date': str(self.day), 'cast': self.cast.pk, 'version': 0,
                'request_id': str(uuid.uuid4()), 'collected_amount': 15000,
                'unpaid_amount': None, 'memo': '架空データの経理確認', **changes}

    def checkout(self):
        response = self.cast_client.post('/api/cast/checkout/', {'date': str(self.day),
            'checklist_json': {'room_cleaned': True}}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def test_checklist_has_no_financial_effect_and_next_day_has_no_auto_carry(self):
        old = CastDailyCheckout.objects.create(store=self.store, cast=self.cast,
            date=self.day - timedelta(days=1), estimated_pay=20000)
        before = list(RoomCashMovement.objects.values_list('pk', flat=True))
        data = self.checkout()
        cancellation = self.manager_client.get(f'/api/orders/{self.order.pk}/cancellation-checkout/')
        self.assertIsNone(cancellation.data['checkout'])
        self.assertFalse(data['cash_handover_recorded'])
        for field in ['room_cash_taken_amount', 'carryover_opening_amount', 'carryover_closing_amount']:
            self.assertIsNone(data[field])
        self.assertFalse(EnvelopeSubmission.objects.exists())
        self.assertEqual(before, list(RoomCashMovement.objects.values_list('pk', flat=True)))
        tomorrow = self.cast_client.get('/api/cast/checkout/', {'date': str(self.day + timedelta(days=1))})
        self.assertEqual(tomorrow.data['settlement_mode'], 'DEFERRED')
        self.assertIsNone(tomorrow.data['carryover_opening_amount'])
        old.refresh_from_db()
        self.assertEqual(old.estimated_pay, 20000)
        row = self.manager_client.get('/api/op/daily-settlement/', {'date': str(self.day)}).data['rows'][0]
        self.assertEqual(row['settlement_mode'], 'DEFERRED')
        self.assertFalse(row['can_register_by_store'])
        self.assertNotIn('receivable_amount', row)
        self.assertEqual(row['cash_settlement_amount'], 15000)

    def test_late_confirmation_without_checkout_including_locked_day_and_explicit_zero(self):
        DailySettlement.objects.create(store=self.store, date=self.day, status='LOCKED')
        response = self.manager_client.post(self.url, self.payload(collected_amount=0, unpaid_amount=0), format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['collected_amount'], 0)
        self.assertFalse(CastDailyCheckout.objects.exists())
        self.assertEqual(CastAccountingConfirmationEvent.objects.count(), 1)
        data = self.cast_client.get('/api/cast/checkout/', {'date': str(self.day)}).data
        self.assertEqual(data['confirmed_unpaid'], {'amount': 0, 'date': str(self.day)})
        self.assertIsNone(data['carryover_opening_amount'])

    def test_unpaid_is_latest_confirmed_total_not_sum_or_cash_difference(self):
        for i, amount in enumerate([10000, 3000]):
            response = self.manager_client.post(self.url, self.payload(date=str(self.day + timedelta(days=i)),
                unpaid_amount=amount, collected_amount=40000), format='json')
            self.assertEqual(response.status_code, 200, response.data)
        data = self.cast_client.get('/api/cast/checkout/', {'date': str(self.day + timedelta(days=2))}).data
        self.assertEqual(data['confirmed_unpaid']['amount'], 3000)
        self.assertIsNone(data['carryover_opening_amount'])

    def test_unknown_is_not_zero_and_read_does_not_write(self):
        response = self.manager_client.get(self.url, {'date': str(self.day)})
        self.assertEqual(response.data['rows'], [])
        self.assertFalse(CastAccountingConfirmation.objects.exists())
        response = self.manager_client.post(self.url, self.payload(collected_amount=None), format='json')
        self.assertIsNone(response.data['collected_amount'])
        self.assertIsNone(response.data['unpaid_amount'])
        self.assertIsNone(self.cast_client.get('/api/cast/checkout/', {'date': str(self.day)}).data['confirmed_unpaid'])

    def test_old_pending_dates_do_not_open_old_money_entry_as_default_after_cutover(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        with patch('django.utils.timezone.now', return_value=datetime(2026, 10, 3, 20, tzinfo=ZoneInfo('Asia/Tokyo'))):
            data = self.cast_client.get('/api/cast/checkout/').data
        self.assertEqual(data['date'], '2026-10-03')
        self.assertEqual(data['settlement_mode'], 'DEFERRED')
        self.assertIn('2026-10-02', data['pending_dates'])

    def test_retry_conflicts_and_audit_history(self):
        body = self.payload(unpaid_amount=1000)
        first = self.manager_client.post(self.url, body, format='json')
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(self.manager_client.post(self.url, body, format='json').status_code, 200)
        self.assertEqual(CastAccountingConfirmationEvent.objects.count(), 1)
        self.assertEqual(self.manager_client.post(self.url, {**body, 'unpaid_amount': 2}, format='json').status_code, 409)
        self.assertEqual(self.manager_client.post(self.url, self.payload(), format='json').status_code, 409)
        edit = self.manager_client.post(self.url, self.payload(version=1, unpaid_amount=0), format='json')
        self.assertEqual(edit.status_code, 200)
        row = self.manager_client.get(self.url, {'date': str(self.day)}).data['rows'][0]
        self.assertEqual(len(row['history']), 2)
        self.assertEqual(row['history'][0]['before']['unpaid_amount'], 1000)
        self.assertEqual(row['history'][0]['after']['unpaid_amount'], 0)

    def test_invalid_input_and_role_tenant_denials(self):
        for value in [-1, True, '', 1.5, '100', 2147483648]:
            response = self.manager_client.post(self.url, self.payload(unpaid_amount=value), format='json')
            self.assertEqual(response.status_code, 400, (value, response.data))
        for client in [APIClient(), self.cast_client]:
            self.assertEqual(client.post(self.url, self.payload(), format='json').status_code, 403)
            self.assertEqual(client.get(self.url, {'date': str(self.day)}).status_code, 403)
        other = Store.objects.create(name='境界確認用')
        user = get_user_model().objects.create_user('deferred-other')
        UserProfile.objects.create(user=user, store=other, role='manager')
        client = APIClient(); client.force_authenticate(user)
        self.assertEqual(client.post(self.url, self.payload(), format='json').status_code, 404)
        self.assertEqual(client.get(self.url, {'date': str(self.day)}).data['rows'], [])

    def test_legacy_routes_cannot_record_deferred_financial_values(self):
        self.assertEqual(self.cast_client.post('/api/cast/checkout/', {'date': str(self.day),
            'room_cash_taken_amount': 0}, format='json').status_code, 400)
        data = self.checkout()
        for path, body, method in [
            ('cash-settlement', {'room_cash_taken_amount': 1000}, 'patch'),
            ('cash-receipt-correction', {'room_cash_taken_amount': 1000}, 'patch'),
            ('office-payment', {'amount': 1000}, 'post'),
        ]:
            response = getattr(self.manager_client, method)(f"/api/cast-checkouts/{data['id']}/{path}/", body, format='json')
            self.assertEqual(response.status_code, 400, response.data)
        register = self.manager_client.post('/api/cast-checkouts/register-by-store/', self.payload(), format='json')
        self.assertEqual(register.status_code, 400, register.data)

    def test_new_accounting_does_not_touch_room_projection_or_old_snapshots(self):
        before = self.manager_client.get('/api/cast-checkouts/room-cash/', {'date': str(self.day)}).data
        self.assertEqual(self.manager_client.post(self.url, self.payload(unpaid_amount=10000), format='json').status_code, 200)
        self.assertEqual(before, self.manager_client.get('/api/cast-checkouts/room-cash/', {'date': str(self.day)}).data)
        self.assertFalse(CastDailyCheckout.objects.exists())

    def test_failed_audit_rolls_back_money_and_confirmation(self):
        with patch('core.models.CastAccountingConfirmationEvent.objects.create', side_effect=RuntimeError('audit failed')):
            with self.assertRaises(RuntimeError):
                self.manager_client.post(self.url, self.payload(), format='json')
        self.assertFalse(CastAccountingConfirmation.objects.exists())

    def test_seed_is_staging_only_and_creates_isolated_synthetic_accounts(self):
        import io
        import json
        import os
        from django.core.management import call_command
        from django.core.management.base import CommandError
        from django.test import override_settings
        payload = {'slug': 'settlement-demo-test', **{role: {
            'username': 'settlement-demo-test-' + role, 'password': 'synthetic-test-only-12345'}
            for role in ('manager', 'cast', 'staff')}}
        with patch.dict(os.environ, {'DJANGO_ENV': 'production'}):
            with self.assertRaises(CommandError):
                call_command('seed_settlement_demo')
        with patch.dict(os.environ, {'DJANGO_ENV': 'staging'}), override_settings(SMS_DUMMY_MODE=True):
            output = io.StringIO()
            with patch('sys.stdin', io.StringIO(json.dumps(payload))):
                call_command('seed_settlement_demo', stdout=output)
            demo = Store.objects.get(slug='settlement-demo-test')
            self.assertNotEqual(demo.pk, self.store.pk)
            self.assertFalse(demo.line_is_enabled)
            self.assertEqual(demo.casts.count(), 3)
            self.assertEqual(CastAccountingConfirmation.objects.filter(store=demo).count(), 3)
            with patch('sys.stdin', io.StringIO(json.dumps(payload))):
                with self.assertRaises(CommandError):
                    call_command('seed_settlement_demo', stdout=output)
