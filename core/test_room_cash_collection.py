import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import datetime, timedelta
from unittest import skipUnless
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient
from core.models import Room, RoomCashCollection, Store, UserProfile
from core.test_room_cash import RoomCashProjectionTests


@patch('core.views.timezone.now', return_value=datetime(2026, 10, 2, 20, tzinfo=ZoneInfo('Asia/Tokyo')))
class RoomCashCollectionTests(TestCase):
    setUp = RoomCashProjectionTests.setUp
    summary = RoomCashProjectionTests.summary
    count = RoomCashProjectionTests.count

    def collect(self, amount=10000, **extra):
        payload = {'date': self.day.isoformat(), 'room': self.room.pk, 'operation': 'collect',
                   'amount': amount, 'memo': '経理回収', 'request_id': str(uuid.uuid4()),
                   'expected_revision': self.summary()['revision'], **extra}
        return self.manager_client.post('/api/cast-checkouts/room-cash/', payload, format='json'), payload

    def cancel(self, collection, **extra):
        return self.manager_client.post('/api/cast-checkouts/room-cash/', {
            'date': self.day.isoformat(), 'room': self.room.pk, 'operation': 'cancel_collection',
            'collection_id': collection.pk, 'expected_revision': self.summary()['revision'], **extra,
        }, format='json')

    def test_partial_full_retry_cancel_and_audit(self, _now):
        self.count(amount=15000)
        response, payload = self.collect()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.summary()['expected_cash_amount'], 5000)
        self.assertEqual(self.manager_client.post('/api/cast-checkouts/room-cash/', payload, format='json').status_code, 200)
        self.assertEqual(RoomCashCollection.objects.count(), 1)
        self.assertEqual(self.collect(amount=5000)[0].status_code, 200)
        self.assertEqual(self.summary()['expected_cash_amount'], 0)
        collection = RoomCashCollection.objects.latest('pk')
        self.assertEqual(self.cancel(collection).status_code, 200)
        self.assertEqual(self.cancel(collection).status_code, 200)
        row = self.summary()
        self.assertEqual(row['expected_cash_amount'], 5000)
        self.assertTrue(row['collections'][0]['cancelled_at'])
        self.assertEqual(row['collections'][0]['memo'], '経理回収')
        collection.refresh_from_db()
        self.assertEqual(collection.cancelled_by, self.manager_client.handler._force_user)
        self.assertEqual(self.order.total_price, 24000)

    def test_recount_then_cancel_and_following_day_carry(self, _now):
        self.count(amount=15000)
        self.collect()
        self.count(amount=5000)
        self.assertEqual(self.summary()['expected_cash_amount'], 5000)
        self.cancel(RoomCashCollection.objects.get())
        self.assertEqual(self.summary()['expected_cash_amount'], 15000)
        _now.return_value += timedelta(days=1)
        next_day = self.manager_client.get('/api/cast-checkouts/room-cash/?date=2026-10-03').data['rooms'][0]
        self.assertEqual(next_day['expected_cash_amount'], 15000)

    def test_correction_changes_projection_not_sale_and_requires_recount(self, _now):
        self.count(amount=15000)
        self.collect()
        self.order.total_price += 1000
        self.order.save(update_fields=['total_price'])
        self.assertEqual(self.summary()['expected_cash_amount'], 6000)
        self.assertEqual(self.collect(amount=1000)[0].status_code, 400)
        self.count(amount=6000)
        self.assertEqual(self.collect(amount=1000)[0].status_code, 200)
        self.assertEqual(self.summary()['expected_cash_amount'], 5000)

    def test_unknown_excess_invalid_stale_and_request_reuse(self, _now):
        self.assertEqual(self.collect()[0].status_code, 400)
        self.count(amount=15000)
        for value in (0, -1, True, 1.5, '1.5', None, 15001):
            self.assertEqual(self.collect(amount=value)[0].status_code, 400)
        row = self.summary()
        response, payload = self.collect()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.collect(amount=1000, expected_revision=row['revision'])[0].status_code, 409)
        self.assertEqual(self.collect(amount=1000, request_id=payload['request_id'])[0].status_code, 409)

    def test_roles_rooms_and_cast_history_privacy(self, _now):
        self.count(amount=15000)
        self.collect()
        row = self.cast_client.get('/api/cast/room-cash/?date=2026-10-02').data['rooms'][0]
        self.assertEqual(row['expected_cash_amount'], 5000)
        self.assertNotIn('collections', row)
        body = {'operation': 'collect', 'date': self.day.isoformat(), 'room': self.room.pk, 'amount': 1}
        staff = get_user_model().objects.create_user('collection-staff')
        UserProfile.objects.create(user=staff, store=self.store, role='staff')
        staff_client = APIClient(); staff_client.force_authenticate(staff)
        for client in (self.cast_client, staff_client, APIClient()):
            self.assertEqual(client.post('/api/cast-checkouts/room-cash/', body, format='json').status_code, 403)
        other = Room.objects.create(store=Store.objects.create(name='別店舗'), name='別室')
        self.assertEqual(self.collect(amount=1, room=other.pk)[0].status_code, 400)
        self.assertEqual(self.collect(amount=1, date='2026-10-01')[0].status_code, 400)


@skipUnless(connection.vendor == 'postgresql', 'PostgreSQL row locks are required')
@patch('core.views.timezone.now', return_value=datetime(2026, 10, 2, 20, tzinfo=ZoneInfo('Asia/Tokyo')))
class RoomCashCollectionConcurrencyTests(TransactionTestCase):
    setUp = RoomCashProjectionTests.setUp
    summary = RoomCashProjectionTests.summary
    count = RoomCashProjectionTests.count

    def race(self, same_request=False, with_count=False):
        self.count(amount=15000)
        row = self.summary()
        actor = self.manager_client.handler._force_user
        key = str(uuid.uuid4())
        barrier = Barrier(2)

        def send(index):
            close_old_connections()
            try:
                client = APIClient(); client.force_authenticate(actor)
                payload = {'date': self.day.isoformat(), 'room': self.room.pk,
                           'expected_revision': row['revision'],
                           'request_id': key if same_request else str(uuid.uuid4())}
                payload.update({'actual_cash_amount': 15000} if with_count and index == 1 else
                               {'operation': 'collect', 'amount': 10000})
                barrier.wait(timeout=10)
                return client.post('/api/cast-checkouts/room-cash/', payload, format='json').status_code
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(send, i) for i in range(2)]
            statuses = sorted(f.result(timeout=30) for f in futures)
        self.assertEqual(statuses, [200, 200] if same_request else [200, 409])
        if not with_count:
            self.assertEqual(RoomCashCollection.objects.count(), 1)
            self.assertEqual(self.summary()['expected_cash_amount'], 5000)
        else:
            self.assertIn(self.summary()['expected_cash_amount'], (5000, 15000))

    def test_simultaneous_collections_cannot_overdraw(self, _now):
        self.race()

    def test_simultaneous_retry_collects_only_once(self, _now):
        self.race(same_request=True)

    def test_count_and_collection_share_one_consistent_snapshot(self, _now):
        self.race(with_count=True)
