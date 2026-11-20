from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from core.models import Cast, Room, ShiftAssignment, Order, OperatorNotification, UserProfile, Customer
from core.services.free_booking_capacity import can_place_requests
from core import test_public_web_booking as booking_helpers

TOKYO = booking_helpers.TOKYO


@override_settings(FRONTEND_URL='https://roomink.example', SMS_DUMMY_MODE=True,
                  RESERVATION_LINK_BASE_URL='https://r.roomink.example',
                  EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class FreeBookingQueueTest(TestCase):
    setUp = booking_helpers.PublicWebBookingTest.setUp
    payload = booking_helpers.PublicWebBookingTest.payload
    request_code = booking_helpers.PublicWebBookingTest.request_code

    def add_cast(self, index, room=None):
        cast = Cast.objects.create(store=self.store, name=f'担当{index}')
        room = room or Room.objects.create(store=self.store, name=f'部屋{index}')
        ShiftAssignment.objects.create(store=self.store, cast=cast, room=room,
            date=self.business_date, start_time=time(12), end_time=time(15))
        return cast

    def book(self, index=0, **kwargs):
        requested = self.request_code(cast='free', phone=f'09012345{index:03d}', **kwargs)
        if requested.status_code != 201:
            return requested
        return self.client.post('/api/public/booking/confirm/', {
            'verification_id': requested.data['verification_id'], 'code': '123456',
        }, format='json')

    def manager_client(self, store=None):
        store = store or self.store
        user = get_user_model().objects.create_user(username=f'manager{store.pk}', password='test')
        UserProfile.objects.create(user=user, store=store, role=UserProfile.Role.MANAGER)
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_five_staff_accept_five_pending_requests_but_not_six(self):
        for index in range(4):
            self.add_cast(index)
        for index in range(5):
            result = self.book(index)
            self.assertEqual(result.status_code, 201, result.data)
            self.assertEqual(result.data['cast_name'], 'フリー')
        self.assertEqual(Order.objects.filter(is_free_pending=True).count(), 5)
        self.assertEqual(self.book(6).status_code, 409)
        self.assertEqual(OperatorNotification.objects.count(), 5)
        self.assertIn('担当選択待ち', OperatorNotification.objects.first().title)

    def test_shared_room_does_not_count_as_two_available_slots(self):
        self.add_cast(2, room=self.room)
        self.assertEqual(self.book(0).status_code, 201)
        self.assertEqual(self.book(1).status_code, 409)

    def test_slot_enumeration_reads_capacity_once_for_all_times(self):
        for index in range(4):
            self.add_cast(index)
        self.assertEqual(self.book().status_code, 201)
        with CaptureQueriesContext(connection) as queries:
            result = self.client.get('/api/public/booking/slots/', {
                'store': self.store.pk, 'cast': 'free', 'course': self.course.pk,
                'date': str(self.business_date),
            })
        self.assertEqual(result.status_code, 200, result.data)
        self.assertTrue(result.data['slots'])
        self.assertLess(len(queries), 100)

    def test_cancellation_releases_capacity_and_duplicate_confirmation_does_not(self):
        result = self.book()
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(self.book(1).status_code, 409)
        order = Order.objects.get(pk=result.data['id'])
        order.status = Order.Status.CANCELLED
        order.save(update_fields=['status'])
        self.assertEqual(self.book(2).status_code, 201)

    def test_assignment_keeps_order_and_free_price_and_requires_staff(self):
        result = self.book()
        pk = result.data['id']
        other = self.manager_client(self.other_store)
        self.assertEqual(other.patch(f'/api/orders/{pk}/', {'cast': self.cast.pk}, format='json').status_code, 404)
        client = self.manager_client()
        self.assertEqual(client.post(f'/api/orders/{pk}/confirm/').status_code, 400)
        changed = client.patch(f'/api/orders/{pk}/', {'cast': self.cast.pk, 'expected_updated_at': Order.objects.get(pk=pk).updated_at.isoformat()}, format='json')
        self.assertEqual(changed.status_code, 200, changed.data)
        order = Order.objects.get(pk=pk)
        self.assertFalse(order.is_free_pending)
        self.assertEqual(order.cast_id, self.cast.pk)
        self.assertEqual(order.room_id, self.room.pk)
        self.assertEqual(order.nomination_fee_price, 0)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(client.post(f'/api/orders/{pk}/confirm/').status_code, 200)
        self.assertEqual(client.post(f'/api/orders/{pk}/confirm/').status_code, 400)

    def test_named_booking_cannot_take_capacity_already_accepted_as_free(self):
        self.assertEqual(self.book().status_code, 201)
        result = self.request_code(phone='09099998888', cast=self.cast.pk, nomination_mode='automatic')
        self.assertEqual(result.status_code, 409, result.data)

    def test_stale_assignment_cannot_overwrite_staff_choice(self):
        result = self.book()
        pk = result.data['id']
        client = self.manager_client()
        revision = Order.objects.get(pk=pk).updated_at.isoformat()
        body = {'cast': self.cast.pk, 'expected_updated_at': revision}
        self.assertEqual(client.patch(f'/api/orders/{pk}/', body, format='json').status_code, 200)
        self.assertEqual(client.patch(f'/api/orders/{pk}/', body, format='json').status_code, 409)

    def test_cast_ng_is_rechecked_when_staff_assigns_pending_request(self):
        result = self.book()
        order = Order.objects.get(pk=result.data['id'])
        order.customer.flag = order.customer.Flag.BAN
        order.customer.ban_type = order.customer.BanType.CAST_NG
        order.customer.save()
        order.customer.ng_casts.add(self.cast)
        client = self.manager_client()
        response = client.patch(f'/api/orders/{order.pk}/', {
            'cast': self.cast.pk, 'expected_updated_at': order.updated_at.isoformat(),
        }, format='json')
        self.assertEqual(response.status_code, 400, response.data)
        order.refresh_from_db()
        self.assertTrue(order.is_free_pending)

    def test_queue_cast_is_not_an_extra_public_therapist(self):
        queue = Cast.objects.create(store=self.store, name='フリー', is_booking_queue=True)
        ShiftAssignment.objects.create(store=self.store, cast=queue, room=self.room,
            date=self.business_date, start_time=time(12), end_time=time(15))
        response = self.client.get('/api/public/booking/options/', {'store': self.store.pk, 'date': str(self.business_date)})
        self.assertNotIn(queue.pk, [item['id'] for item in response.data['casts']])
        self.assertEqual(self.book().status_code, 201)
        self.assertEqual(self.book(1).status_code, 409)

    def test_linked_legacy_free_lane_is_migrated_and_reused_without_extra_capacity(self):
        from importlib import import_module
        from django.apps import apps

        user = get_user_model().objects.create_user(username='legacy-free-login')
        queue = Cast.objects.create(store=self.store, name='フリー', user=user)
        self.assertTrue(queue.is_booking_queue)
        # Recreate the pre-migration state without invoking the current save.
        Cast.objects.filter(pk=queue.pk).update(is_booking_queue=False)
        migration = import_module('core.migrations.0114_classify_linked_free_booking_queues')
        migration.classify_linked_queues(apps, None)
        queue.refresh_from_db()
        self.assertTrue(queue.is_booking_queue)
        self.assertEqual(queue.user_id, user.pk)
        self.cast.refresh_from_db()
        self.assertFalse(self.cast.is_booking_queue)
        room = Room.objects.create(store=self.store, name='旧フリー枠')
        ShiftAssignment.objects.create(store=self.store, cast=queue, room=room,
            date=self.business_date, start_time=time(12), end_time=time(15))
        response = self.client.get('/api/public/booking/options/', {
            'store': self.store.pk, 'date': str(self.business_date),
        })
        self.assertNotIn(queue.pk, [item['id'] for item in response.data['casts']])
        first = self.book()
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(Order.objects.get(pk=first.data['id']).cast_id, queue.pk)
        self.assertEqual(self.book(1).status_code, 409)

    def test_manual_queue_uses_same_capacity_and_keeps_phone_booking_policy(self):
        queue = Cast.objects.create(store=self.store, name='フリー', is_booking_queue=True)
        customer = Customer.objects.create(store=self.store, phone='09011112222', online_booking_ng=True)
        client = self.manager_client()
        payload = {'customer':customer.pk, 'cast':queue.pk, 'course':self.course.pk,
            'start':datetime(2030,1,15,12,30,tzinfo=TOKYO).isoformat(), 'payment_method':'CASH'}
        response = client.post('/api/orders/', payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data['is_free_pending'])
        self.assertEqual(self.book(1).status_code, 409)

    def test_customer_cannot_book_queue_cast_through_legacy_endpoint(self):
        queue = Cast.objects.create(store=self.store, name='フリー', is_booking_queue=True)
        user = get_user_model().objects.create_user(username='queue-customer')
        Customer.objects.create(store=self.store,user=user,phone='09011112222')
        self.client.force_authenticate(user)
        response = self.client.post('/api/cu/bookings/', {
            'cast':queue.pk, 'course':self.course.pk,
            'start':datetime(2030,1,15,12,30,tzinfo=TOKYO).isoformat(),
        }, format='json')
        self.assertEqual(response.status_code, 403, response.data)
        self.assertEqual(Order.objects.count(), 0)

    def test_matcher_reassigns_flexible_request_to_leave_specialist_available(self):
        start = datetime(2030, 1, 15, 12, tzinfo=TOKYO)
        end = start + timedelta(hours=1)
        flexible = {'start': start, 'end': end, 'options': [(1, 1, 15), (2, 2, 15)]}
        restricted = {'start': start, 'end': end, 'options': [(1, 1, 15)]}
        self.assertTrue(can_place_requests([flexible, restricted]))
        self.assertFalse(can_place_requests([flexible, restricted, restricted]))
