import uuid
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import urlsplit

from django.test import TestCase, override_settings
from django.utils import timezone
from requests.exceptions import Timeout
from twilio.base.exceptions import TwilioRestException
from twilio.request_validator import RequestValidator

from . import test_work_devices as foundation
from .models import CallLog, WorkDevice, WorkDeviceEvent, WorkDeviceStore
from .work_device_views import _issue_credential


class WorkVoiceDemoTest(TestCase):
    personal_login = foundation.WorkDeviceFoundationTest.personal_login

    def setUp(self):
        foundation.WorkDeviceFoundationTest.setUp(self)
        login = self.personal_login(store_ids=[self.store_a.pk])
        self.device = WorkDevice.objects.get(pk=login.data['device']['id'])
        self.data = {'username': self.manager.username, 'password': 'Strong-pass-123'}
        self.config = override_settings(
            WORK_VOICE_DEMO_ENABLED=True, WORK_VOICE_DEMO_STORE_ID=str(self.store_a.pk),
            WORK_VOICE_DEMO_USERNAMES=(self.manager.username,), WORK_VOICE_DEMO_FROM_NUMBER='+12025550123',
            TWILIO_WEBHOOK_PUBLIC_BASE_URL='https://api-staging.roomink.net',
            TWILIO_WORK_ACCOUNT_SID='AC'+'1'*32, TWILIO_WORK_AUTH_TOKEN='work-secret',
            TWILIO_VOICE_API_KEY_SID='SKtest', TWILIO_VOICE_API_KEY_SECRET='test-secret',
            TWILIO_VOICE_PUSH_CREDENTIAL_SID='CRtest',
        )
        self.config.enable()
        self.addCleanup(self.config.disable)
        self.provider = patch('core.work_voice_demo.Client').start()
        self.addCleanup(patch.stopall)

    def devices(self, **data):
        return self.client.post('/api/work/demo/devices/', {**self.data, **data}, format='json')

    def call(self, **data):
        return self.client.post('/api/work/demo/call/',
                                {**self.data, 'device_id': str(self.device.pk), **data}, format='json')

    def callback(self, state, **data):
        url = self.provider.return_value.calls.create.call_args.kwargs['status_callback']
        parts = urlsplit(url)
        payload = {'AccountSid': 'AC'+'1'*32, 'CallStatus': state, **data}
        signature = RequestValidator('work-secret').compute_signature(url, payload)
        return self.client.post(parts.path+'?'+parts.query, payload, HTTP_X_TWILIO_SIGNATURE=signature)

    def test_disabled_or_invalid_config_never_calls_provider(self):
        for config in ({'WORK_VOICE_DEMO_ENABLED': False}, {'WORK_VOICE_DEMO_STORE_ID': 'wrong'},
                       {'TWILIO_WEBHOOK_PUBLIC_BASE_URL': 'https://attacker.example'},
                       {'TWILIO_VOICE_PUSH_CREDENTIAL_SID': ''}):
            with override_settings(**config):
                self.assertEqual(self.call().status_code, 403)
        self.provider.assert_not_called()
        self.assertFalse(CallLog.objects.exists())

    def test_credentials_and_account_allowlist_are_required(self):
        self.assertEqual(self.devices(username=self.outsider.username).status_code, 403)
        self.assertEqual(self.devices(password='wrong').status_code, 403)
        self.assertEqual(self.client.post('/api/work/demo/call/', {}, format='json').status_code, 400)
        self.provider.assert_not_called()

    def test_devices_exclude_other_owners_stores_and_unavailable_receivers(self):
        own = self.devices()
        self.assertEqual([d['id'] for d in own.data['devices']], [str(self.device.pk)])
        for config in ({'status': 'paused'}, {'platform': 'android'}, {'owner': self.outsider}):
            WorkDevice.objects.create(device_key=uuid.uuid4(), kind='personal', label='Excluded',
                **{'platform': 'ios', 'status': 'active', 'owner': self.manager, **config})
        foreign = WorkDevice.objects.create(device_key=uuid.uuid4(), kind='personal', label='Other store',
                                           platform='ios', owner=self.manager)
        WorkDeviceStore.objects.create(device=foreign, store=self.store_b)
        _issue_credential(foreign)
        self.assertEqual(len(self.devices().data['devices']), 1)
        self.assertEqual(self.call(device_id=str(foreign.pk)).status_code, 403)
        self.device.store_subscriptions.update(is_receiving=False)
        self.assertEqual(self.devices().data['devices'], [])
        self.assertEqual(self.call().status_code, 403)
        self.provider.assert_not_called()

    def test_membership_or_device_credential_revocation_denies_calls(self):
        self.device.credentials.update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.call().status_code, 403)
        self.manager.store_memberships.filter(store=self.store_a).update(is_active=False)
        self.assertEqual(self.devices().status_code, 403)
        self.provider.assert_not_called()

    def test_call_targets_only_selected_client_and_creates_scoped_history(self):
        self.assertEqual(self.call(to='+819012345678', store_id=self.store_c.pk).status_code, 202)
        kwargs = self.provider.return_value.calls.create.call_args.kwargs
        self.assertEqual(kwargs['to'], 'client:roomink_work_'+self.device.pk.hex)
        self.assertEqual(kwargs['time_limit'], 30)
        self.assertNotIn('record', kwargs)
        call = CallLog.objects.get()
        self.assertEqual(call.store_id, self.store_a.pk)
        self.assertEqual(call.from_phone, 'テスト着信')
        self.assertEqual(WorkDeviceEvent.objects.get(action='demo_call_requested').actor_id, self.manager.pk)

    def test_rate_limits_persist_attempts_and_apply_store_wide(self):
        self.assertEqual(self.call().status_code, 202)
        self.assertEqual(self.call().status_code, 429)
        WorkDeviceEvent.objects.filter(action='demo_call_requested').update(created_at=timezone.now()-timedelta(minutes=2))
        for _ in range(19):
            WorkDeviceEvent.objects.create(action='demo_call_requested', store=self.store_a)
        WorkDeviceEvent.objects.filter(action='demo_call_requested').update(created_at=timezone.now()-timedelta(minutes=2))
        self.assertEqual(self.call().status_code, 429)
        self.assertEqual(self.provider.return_value.calls.create.call_count, 1)

    def test_provider_failure_does_not_allow_immediate_retry(self):
        self.provider.return_value.calls.create.side_effect = TwilioRestException(400, 'test')
        self.assertEqual(self.call().status_code, 502)
        self.assertEqual(CallLog.objects.get().status, CallLog.Status.MISSED)
        self.assertEqual(self.call().status_code, 429)

    def test_network_timeout_keeps_callback_reconcilable(self):
        self.provider.return_value.calls.create.side_effect = Timeout()
        self.assertEqual(self.call().status_code, 502)
        self.assertEqual(CallLog.objects.get().status, CallLog.Status.NEW)
        self.assertEqual(self.callback('completed', CallDuration='9').status_code, 200)
        self.assertEqual(CallLog.objects.get().status, CallLog.Status.DONE)

    def test_callbacks_require_signature_account_and_store_and_are_terminal(self):
        self.call()
        url = self.provider.return_value.calls.create.call_args.kwargs['status_callback']
        parts = urlsplit(url)
        self.assertEqual(self.client.post(parts.path+'?'+parts.query, {}).status_code, 403)
        self.assertEqual(self.callback('completed', AccountSid='AC'+'2'*32).status_code, 403)
        with override_settings(WORK_VOICE_DEMO_STORE_ID=str(self.store_b.pk)):
            self.callback('completed', CallDuration='9')
        self.assertEqual(CallLog.objects.get().status, CallLog.Status.NEW)
        self.callback('in-progress')
        self.callback('completed', CallDuration='9')
        self.callback('ringing')
        self.callback('failed')
        call = CallLog.objects.get()
        self.assertEqual(call.status, CallLog.Status.DONE)
        self.assertEqual(call.duration_seconds, 9)

    def test_missed_callback_and_other_request_cannot_change_calls(self):
        self.call()
        self.callback('no-answer')
        self.assertEqual(CallLog.objects.get().status, CallLog.Status.MISSED)
        self.callback('completed', CallDuration='12')
        self.assertEqual(CallLog.objects.get().status, CallLog.Status.MISSED)
