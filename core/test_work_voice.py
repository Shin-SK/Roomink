from django.test import TestCase, override_settings
from django.core.cache import cache
from twilio.request_validator import RequestValidator
from .models import CallLog, WorkDevice
from .models import WorkDeviceStore
from .work_device_views import _issue_credential
import uuid
from . import test_work_devices as foundation


class WorkVoiceIsolationTest(TestCase):
    personal_login = foundation.WorkDeviceFoundationTest.personal_login
    def setUp(self):
        cache.clear()
        foundation.WorkDeviceFoundationTest.setUp(self)
        login = self.personal_login(store_ids=[self.store_a.pk])
        self.device = WorkDevice.objects.get(pk=login.data['device']['id'])
        self.voice_settings = override_settings(
            WORK_VOICE_TEST_ENABLED=True, WORK_VOICE_ENV='staging',
            TWILIO_WORK_ACCOUNT_SID='AC' + '1' * 32,
            TWILIO_WORK_AUTH_TOKEN='isolated-test-secret',
            WORK_VOICE_TEST_DEVICE_ID=str(self.device.pk),
            WORK_VOICE_TEST_STORE_ID=str(self.store_a.pk),
            WORK_VOICE_TEST_NUMBER='+12025550123',
        )
        self.voice_settings.enable()
        self.addCleanup(self.voice_settings.disable)
        self.data = {'AccountSid': 'AC' + '1' * 32, 'CallSid': 'CA' + '2' * 32,
                     'To': '+12025550123', 'From': '+12025550124'}

    def signed(self, path, data=None):
        data = data or self.data
        signature = RequestValidator('isolated-test-secret').compute_signature(
            'https://api-staging.roomink.net' + path, data)
        return self.client.post(path, data, HTTP_X_TWILIO_SIGNATURE=signature)

    def test_signed_call_routes_only_to_selected_work_identity(self):
        response = self.signed('/api/work/voice-test/incoming/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'roomink_work_' + self.device.pk.hex)
        self.assertContains(response, 'timeLimit="120"')
        self.assertNotContains(response, '<Sip>')
        self.assertEqual(CallLog.objects.get().store_id, self.store_a.pk)

    def test_invalid_signature_and_parent_account_cannot_create_calls(self):
        self.assertEqual(self.client.post('/api/work/voice-test/incoming/', self.data).status_code, 403)
        self.data['AccountSid'] = 'AC' + '3' * 32
        self.assertEqual(self.signed('/api/work/voice-test/incoming/').status_code, 403)
        self.assertFalse(CallLog.objects.exists())

    def test_production_and_disabled_experiment_refuse_even_signed_calls(self):
        for config in ({'WORK_VOICE_ENV': 'production'}, {'WORK_VOICE_TEST_ENABLED': False}):
            with override_settings(**config):
                self.assertEqual(self.signed('/api/work/voice-test/incoming/').status_code, 403)
        self.assertFalse(CallLog.objects.exists())

    def test_other_number_store_and_receiving_off_never_ring(self):
        self.data['To'] = '+12025550125'
        self.assertContains(self.signed('/api/work/voice-test/incoming/'), '<Reject')
        self.data['To'] = '+12025550123'
        with override_settings(WORK_VOICE_TEST_STORE_ID=str(self.store_c.pk)):
            self.assertContains(self.signed('/api/work/voice-test/incoming/'), '<Reject')
        self.device.store_subscriptions.update(is_receiving=False)
        self.assertContains(self.signed('/api/work/voice-test/incoming/'), '<Reject')
        self.assertFalse(CallLog.objects.exists())

    def test_replayed_callbacks_do_not_change_final_state_or_ordinary_cti(self):
        self.signed('/api/work/voice-test/incoming/')
        ordinary = CallLog.objects.create(store=self.store_a, contact_id=self.data['CallSid'],
                                          from_phone='', to_phone='')
        data = {**self.data, 'DialCallStatus': 'completed', 'DialCallDuration': '11'}
        self.signed('/api/work/voice-test/finished/', data)
        self.signed('/api/work/voice-test/finished/', {**data, 'DialCallStatus': 'no-answer'})
        call = CallLog.objects.get(contact_id='work-test:' + self.data['CallSid'])
        self.assertEqual(call.status, CallLog.Status.DONE)
        self.assertEqual(call.duration_seconds, 11)
        ordinary.refresh_from_db()
        self.assertEqual(ordinary.status, CallLog.Status.NEW)

    def test_trial_stops_after_five_unique_calls(self):
        for index in range(5):
            data = {**self.data, 'CallSid': 'CA' + format(index, '032x')}
            self.assertContains(self.signed('/api/work/voice-test/incoming/', data), '<Client')
        self.assertContains(self.signed('/api/work/voice-test/incoming/'), '<Reject')
        self.assertEqual(CallLog.objects.count(), 5)

    def additional_device(self, *, owner=None, store=None, receiving=True, status='active'):
        device = WorkDevice.objects.create(device_key=uuid.uuid4(), kind='personal',
            owner=owner or self.manager, platform='ios', label='Additional test phone', status=status)
        WorkDeviceStore.objects.create(device=device, store=store or self.store_a,
                                       is_receiving=receiving)
        _issue_credential(device)
        return device

    def test_three_entitled_devices_share_one_parent_call(self):
        second = self.additional_device()
        third = self.additional_device()
        response = self.signed('/api/work/voice-test/incoming/')
        for device in (self.device, second, third):
            self.assertContains(response, 'roomink_work_' + device.pk.hex)
        self.assertEqual(response.content.count(b'<Client '), 3)
        self.assertEqual(CallLog.objects.count(), 1)

    def test_off_paused_revoked_credentials_and_foreign_store_devices_do_not_ring(self):
        excluded = [self.additional_device(receiving=False),
                    self.additional_device(status='paused'),
                    self.additional_device(store=self.store_c),
                    self.additional_device(owner=self.outsider),
                    self.additional_device()]
        from django.utils import timezone
        excluded[-1].credentials.update(revoked_at=timezone.now())
        response = self.signed('/api/work/voice-test/incoming/')
        for device in excluded:
            self.assertNotContains(response, 'roomink_work_' + device.pk.hex)
        self.assertContains(response, 'roomink_work_' + self.device.pk.hex)

    def test_losing_child_does_not_mark_answered_parent_missed(self):
        self.additional_device()
        self.signed('/api/work/voice-test/incoming/')
        path = '/api/work/voice-test/finished/?parent=' + self.data['CallSid']
        self.signed(path, {**self.data, 'CallStatus': 'in-progress'})
        self.signed(path, {**self.data, 'CallSid': 'CA' + '5' * 32, 'CallStatus': 'canceled'})
        self.assertEqual(CallLog.objects.get().status, CallLog.Status.IN_PROGRESS)
        self.signed(path, {**self.data, 'CallStatus': 'completed', 'CallDuration': '9'})
        self.signed(path, {**self.data, 'CallSid': 'CA' + '5' * 32, 'CallStatus': 'busy'})
        self.assertEqual(CallLog.objects.get().status, CallLog.Status.DONE)

    def test_more_than_ten_receivers_fail_closed(self):
        for _ in range(10):
            self.additional_device()
        self.assertContains(self.signed('/api/work/voice-test/incoming/'), '<Reject')
        self.assertFalse(CallLog.objects.exists())

    def test_caller_hangup_and_delayed_child_completion_leave_correct_history(self):
        self.signed('/api/work/voice-test/incoming/')
        self.signed('/api/work/voice-test/finished/', {**self.data, 'CallStatus': 'completed'})
        call = CallLog.objects.get()
        self.assertEqual(call.status, CallLog.Status.MISSED)
        child_path = '/api/work/voice-test/finished/?parent=' + self.data['CallSid']
        self.signed(child_path, {**self.data, 'CallSid': 'CA' + '4' * 32,
                                 'CallStatus': 'completed', 'CallDuration': '8'})
        call.refresh_from_db()
        self.assertEqual(call.status, CallLog.Status.DONE)
        self.assertEqual(call.duration_seconds, 8)
        self.signed('/api/work/voice-test/finished/', {**self.data, 'CallStatus': 'completed'})
        call.refresh_from_db()
        self.assertEqual(call.status, CallLog.Status.DONE)
