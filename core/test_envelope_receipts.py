import uuid
from unittest.mock import patch
from datetime import datetime
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from core import test_sales_allocation
from core.models import CastDailyCheckout, DailySettlement, EnvelopeReceiptEvent, EnvelopeSubmission, RoomCashCheckpoint, RoomCashCollection, Store, UserProfile
from core.services.envelope_receipts import capture


@patch('django.utils.timezone.now', return_value=datetime(2026, 10, 2, 22, tzinfo=ZoneInfo('Asia/Tokyo')))
class EnvelopeReceiptTests(TestCase):
    setUp = test_sales_allocation.SalesAllocationTest.setUp
    url = '/api/op/envelope-receipts/'

    def submit(self):
        result = self.cast_client.post('/api/cast/checkout/', {'room_cash_taken_amount': 9000}, format='json')
        self.assertEqual(result.status_code, 201, result.data)
        return CastDailyCheckout.objects.get(pk=result.data['id'])

    def read(self):
        result = self.manager_client.get(self.url, {'date': str(self.day)})
        self.assertEqual(result.status_code, 200, result.data)
        return result.data['rows'][0]

    def write(self, row=None, **changes):
        row = row or self.read()
        body = {'checkout': row['checkout'], 'source_revision': row['source_revision'], 'version': row['version'],
                'action': 'receive', 'actual_amount': row['expected_amount'], 'memo': '', 'request_id': str(uuid.uuid4()), **changes}
        return self.manager_client.post(self.url, body, format='json'), body

    def test_submission_snapshot_and_receipt_do_not_move_money(self, _):
        checkout = self.submit()
        self.assertEqual(self.read()['expected_amount'], 15000)
        before = list(CastDailyCheckout.objects.values())
        response, body = self.write()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data['received'])
        self.assertEqual(response.data['difference_amount'], 0)
        self.assertEqual(list(CastDailyCheckout.objects.values()), before)
        self.assertEqual(RoomCashCollection.objects.count(), 0)
        self.assertEqual(RoomCashCheckpoint.objects.count(), 0)
        self.assertEqual(self.manager_client.post(self.url, body, format='json').status_code, 200)
        self.assertEqual(EnvelopeReceiptEvent.objects.count(), 1)
        self.assertEqual(self.manager_client.post(self.url, {**body, 'actual_amount': 0}, format='json').status_code, 409)
        self.assertEqual(checkout.envelope_submissions.count(), 1)

    def test_difference_validation_history_clear_and_conflict(self, _):
        self.submit()
        self.assertEqual(self.write(actual_amount=14000)[0].status_code, 400)
        old = self.read()
        self.assertEqual(self.write(actual_amount=14000, memo='千円不足')[0].status_code, 200)
        self.assertEqual(self.read()['difference_amount'], -1000)
        self.assertEqual(self.write(row=old)[0].status_code, 409)
        self.assertEqual(self.write(action='clear')[0].status_code, 400)
        self.assertEqual(self.write(action='clear', memo='再確認するため')[0].status_code, 200)
        self.assertFalse(self.read()['received'])
        self.assertEqual(len(self.read()['history']), 2)
        for value in (True, -1, 1.5, 2147483648, None):
            self.assertEqual(self.write(actual_amount=value)[0].status_code, 400)

    def test_correction_and_resubmission_preserve_expectation_and_require_recheck(self, _):
        checkout = self.submit()
        self.write()
        self.order.total_price = 25000
        self.order.save()
        changed = self.read()
        self.assertEqual(changed['expected_amount'], 15000)
        self.assertEqual(changed['current_amount'], 16000)
        self.assertTrue(changed['needs_reconfirmation'])
        self.assertEqual(self.write()[0].status_code, 400)
        self.assertEqual(self.write(memo='訂正後も封筒は15000円と確認')[0].status_code, 200)
        self.assertFalse(self.read()['needs_reconfirmation'])
        checkout.status = 'RETURNED'; checkout.save()
        self.assertFalse(self.read()['can_receive'])
        self.assertEqual(self.write(memo='x')[0].status_code, 400)
        self.submit()
        self.assertEqual(checkout.envelope_submissions.count(), 2)
        self.assertEqual(self.read()['expected_amount'], 16000)
        self.assertTrue(self.read()['needs_reconfirmation'])

    def test_old_records_past_day_and_lock_do_not_invent_snapshot(self, _):
        checkout = CastDailyCheckout.objects.create(store=self.store, cast=self.cast, date=self.day)
        row = self.read()
        self.assertIsNone(row['expected_amount'])
        self.assertEqual(EnvelopeSubmission.objects.count(), 0)
        DailySettlement.objects.create(store=self.store, date=self.day, status='LOCKED')
        self.assertEqual(self.write(actual_amount=20000, memo='旧封筒の実額確認')[0].status_code, 200)
        self.assertIsNone(self.read()['difference_amount'])
        self.assertEqual(self.read()['actual_amount'], 20000)

    def test_zero_and_negative_net_are_not_envelopes(self, _):
        checkout = CastDailyCheckout.objects.create(store=self.store, cast=self.cast, date=self.day, room_cash_taken_amount=24000)
        capture(checkout)
        self.assertEqual(self.read()['expected_amount'], 0)
        self.assertFalse(self.read()['can_receive'])
        self.assertEqual(self.write(actual_amount=0)[0].status_code, 400)
        checkout.room_cash_taken_amount = 26000; checkout.save(); capture(checkout)
        self.assertEqual(self.read()['withdrawal_amount'], 2000)
        self.assertFalse(self.read()['can_receive'])

    def test_roles_and_tenant_boundary(self, _):
        self.submit()
        row = self.read()
        for role in ('staff', 'cast', 'customer'):
            user = get_user_model().objects.create_user('envelope-' + role)
            UserProfile.objects.create(user=user, store=self.store, role=role)
            client = APIClient(); client.force_authenticate(user)
            self.assertEqual(client.get(self.url, {'date': str(self.day)}).status_code, 403)
            self.assertEqual(client.post(self.url, {'checkout': row['checkout']}, format='json').status_code, 403)
        other = Store.objects.create(name='他店舗')
        user = get_user_model().objects.create_user('envelope-foreign-manager')
        UserProfile.objects.create(user=user, store=other, role='manager')
        self.manager_client.force_authenticate(user)
        self.assertEqual(self.manager_client.get(self.url, {'date': str(self.day)}).data['rows'], [])
        self.assertEqual(self.write(row=row)[0].status_code, 404)
        self.assertEqual(APIClient().get(self.url).status_code, 403)
