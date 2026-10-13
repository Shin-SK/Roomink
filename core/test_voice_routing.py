from django.test import TestCase, override_settings
from unittest.mock import patch
from twilio.request_validator import RequestValidator

from .models import CallLog, StorePhoneNumber, VoiceRouteEvent, WorkDevice
from . import test_work_devices as foundation
from .voice_routing import configured, eligible_devices


class VoiceRoutingTest(TestCase):
    setUp = foundation.WorkDeviceFoundationTest.setUp
    personal_login = foundation.WorkDeviceFoundationTest.personal_login
    device_client = foundation.WorkDeviceFoundationTest.device_client
    def test_logout_revokes_only_this_device_and_stops_receiving(self):
        first = self.personal_login()
        second = self.personal_login()
        client = self.device_client(first.data['token'])
        self.assertEqual(client.post('/api/work/logout/', {}, format='json').status_code, 200)
        device = WorkDevice.objects.get(pk=first.data['device']['id'])
        self.assertEqual(device.status, 'revoked')
        self.assertFalse(device.credentials.filter(revoked_at__isnull=True).exists())
        self.assertFalse(device.store_subscriptions.filter(is_receiving=True).exists())
        self.assertEqual(client.get('/api/work/me/').status_code, 403)
        self.assertEqual(self.device_client(second.data['token']).get('/api/work/me/').status_code, 200)

    def test_route_permissions_and_unavailable_work(self):
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get('/api/op/voice-route/').status_code, 403)
        self.client.force_authenticate(self.manager)
        response = self.client.get('/api/op/voice-route/')
        self.assertEqual({s['id'] for s in response.data['stores']}, {self.store_a.pk, self.store_b.pk})
        self.assertEqual(self.client.post('/api/op/voice-route/', {'store_id': self.store_a.pk, 'receiver': 'work'}, format='json').status_code, 400)
        self.assertEqual(self.client.post('/api/op/voice-route/', {'store_id': self.store_c.pk, 'receiver': 'groundwire'}, format='json').status_code, 400)

    @override_settings(WORK_VOICE_ROUTING_ENABLED=True,
        TWILIO_ACCOUNT_SID='ACtest', TWILIO_WORK_ACCOUNT_SID='ACtest',
        TWILIO_AUTH_TOKEN='test-secret', TWILIO_WEBHOOK_PUBLIC_BASE_URL='https://api-staging.roomink.net',
        TWILIO_VOICE_API_KEY_SID='SKtest', TWILIO_VOICE_API_KEY_SECRET='test-secret',
        TWILIO_VOICE_PUSH_CREDENTIAL_SID='CRtest')
    def test_switch_audit_and_recovery_when_configuration_breaks(self):
        self.personal_login(store_ids=[self.store_a.pk])
        self.assertEqual(len(eligible_devices(self.store_a.pk)), 1)
        self.client.force_authenticate(self.manager)
        payload = {'store_id': self.store_a.pk, 'receiver': 'work'}
        self.assertEqual(self.client.post('/api/op/voice-route/', payload, format='json').status_code, 200)
        self.assertEqual(self.client.post('/api/op/voice-route/', payload, format='json').status_code, 200)
        self.assertEqual(VoiceRouteEvent.objects.count(), 1)
        with override_settings(TWILIO_WORK_ACCOUNT_SID='ACdifferent'):
            self.assertFalse(configured())
            payload['receiver'] = 'groundwire'
            self.assertEqual(self.client.post('/api/op/voice-route/', payload, format='json').status_code, 200)
        self.assertEqual(VoiceRouteEvent.objects.count(), 2)
        self.store_a.refresh_from_db()
        self.assertEqual(self.store_a.voice_receiver, 'groundwire')

    @override_settings(WORK_VOICE_ROUTING_ENABLED=True,
        TWILIO_ACCOUNT_SID='ACtest', TWILIO_WORK_ACCOUNT_SID='ACtest',
        TWILIO_AUTH_TOKEN='test-secret', TWILIO_WEBHOOK_PUBLIC_BASE_URL='https://api-staging.roomink.net',
        TWILIO_VOICE_API_KEY_SID='SKtest', TWILIO_VOICE_API_KEY_SECRET='test-secret',
        TWILIO_VOICE_PUSH_CREDENTIAL_SID='CRtest')
    def test_real_webhook_work_and_groundwire_escape_path(self):
        login = self.personal_login(store_ids=[self.store_a.pk])
        StorePhoneNumber.objects.create(store=self.store_a, phone='0312345678', is_active=True)
        self.store_a.voice_receiver = 'work'
        self.store_a.save()
        path = '/api/webhook/twilio/voice/'
        data = {'CallSid': 'CA' + '1' * 32, 'From': '+819012345678', 'To': '+81312345678'}
        signature = RequestValidator('test-secret').compute_signature('https://api-staging.roomink.net' + path, data)
        with patch('core.views._store_twilio_sip_uris', return_value=['backup@example.sip.twilio.com']):
            response = self.client.post(path, data, HTTP_X_TWILIO_SIGNATURE=signature)
            self.assertContains(response, '<Client')
            self.assertEqual(CallLog.objects.count(), 1)
            self.device_client(login.data['token']).post('/api/work/logout/', {}, format='json')
            response = self.client.post(path, data, HTTP_X_TWILIO_SIGNATURE=signature)
            self.assertContains(response, '<Sip>')
            self.assertNotContains(response, '<Client')
            self.assertEqual(CallLog.objects.count(), 1)

    @override_settings(TWILIO_AUTH_TOKEN='test-secret', TWILIO_WEBHOOK_PUBLIC_BASE_URL='https://api-staging.roomink.net')
    def test_audio_callbacks_preserve_operator_completion_and_winner_duration(self):
        call = CallLog.objects.create(store=self.store_a, contact_id='CAparent', from_phone='', to_phone='')
        path = '/api/webhook/twilio/work-status/?parent=CAparent'
        def callback(data):
            signature = RequestValidator('test-secret').compute_signature('https://api-staging.roomink.net' + path, data)
            return self.client.post(path, data, HTTP_X_TWILIO_SIGNATURE=signature)
        self.assertEqual(callback({'CallStatus': 'completed', 'CallDuration': '11'}).status_code, 200)
        callback({'CallStatus': 'no-answer', 'CallDuration': '0'})
        call.refresh_from_db()
        self.assertEqual(call.status, CallLog.Status.IN_PROGRESS)
        self.assertEqual(call.duration_seconds, 11)
        call.status = CallLog.Status.DONE
        call.save()
        callback({'CallStatus': 'in-progress'})
        call.refresh_from_db()
        self.assertEqual(call.status, CallLog.Status.DONE)
