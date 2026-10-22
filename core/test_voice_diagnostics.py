import io
from unittest.mock import patch
from urllib.parse import urlencode

from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from twilio.request_validator import RequestValidator

from core.models import CallLog, Store, VoiceDiagnosticEvent
from core.services.voice_diagnostics import record_voice_event


@override_settings(TWILIO_AUTH_TOKEN="diagnostic-test-token", TWILIO_WEBHOOK_PUBLIC_BASE_URL="https://roomink.example", TWILIO_WEBHOOK_ALLOW_UNSIGNED=False)
class VoiceDiagnosticsTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="診断テスト")
        self.call = CallLog.objects.create(store=self.store, contact_id="CAparent", from_phone="09012345678", to_phone="05012345678")
        self.endpoint = "/api/webhook/twilio/diagnostics/"

    def post(self, data, signed=True):
        signature = RequestValidator("diagnostic-test-token").compute_signature("https://roomink.example" + self.endpoint, data) if signed else "invalid"
        return APIClient().post(self.endpoint, urlencode(data), content_type="application/x-www-form-urlencoded", HTTP_X_TWILIO_SIGNATURE=signature)

    def test_signature_and_retry_and_child_correlation(self):
        data = {"CallSid": "CAchild", "ParentCallSid": "CAparent", "CallStatus": "ringing", "SequenceNumber": "1", "From": "09012345678", "ErrorMessage": "secret"}
        self.assertEqual(self.post(data, False).status_code, 403)
        self.assertFalse(VoiceDiagnosticEvent.objects.exists())
        for _ in range(2):
            self.assertEqual(self.post(data).status_code, 200)
        event = VoiceDiagnosticEvent.objects.get()
        self.assertEqual(event.call_id, self.call.pk)
        self.assertEqual(event.call_sid, "CAchild")
        self.assertNotIn("From", event.details)
        self.assertNotIn("secret", str(event.details))

    def test_dial_result_and_out_of_order_do_not_modify_operator_state(self):
        self.call.status = "DONE"
        self.call.save()
        self.assertEqual(self.post({"CallSid": "CAparent", "DialCallStatus": "failed", "DialSipResponseCode": "480"}).status_code, 200)
        self.post({"CallSid": "CAchild", "ParentCallSid": "CAparent", "CallStatus": "initiated", "SequenceNumber": "0"})
        self.call.refresh_from_db()
        self.assertEqual(self.call.status, "DONE")
        self.assertEqual(VoiceDiagnosticEvent.objects.count(), 2)

    def test_storage_failure_does_not_interrupt_and_trace_has_no_phone(self):
        with patch.object(VoiceDiagnosticEvent.objects, "get_or_create", side_effect=RuntimeError("secret")):
            self.assertEqual(self.post({"CallSid": "CAparent", "DialCallStatus": "completed"}).status_code, 200)
        record_voice_event(self.call, "inbound_received", {"CallSid": "CAparent"})
        output = io.StringIO()
        call_command("trace_voice_call", store_id=self.store.pk, call_sid="CAparent", stdout=output)
        self.assertIn("inbound_received", output.getvalue())
        self.assertNotIn(self.call.from_phone, output.getvalue())
        other = io.StringIO()
        call_command("trace_voice_call", store_id=self.store.pk + 1, call_sid="CAparent", stdout=other)
        self.assertEqual(other.getvalue(), "")

    @override_settings(TWILIO_SIP_URI="reception@roomink.sip.twilio.com")
    def test_inbound_twiml_requests_progress_and_dial_result_callbacks(self):
        from xml.etree import ElementTree
        from core.models import StorePhoneNumber
        StorePhoneNumber.objects.create(store=self.store, phone="05012345678", is_active=True)
        endpoint = "/api/webhook/twilio/voice/"
        data = {"CallSid": "CAnew", "From": "+819012345678", "To": "+815012345678", "CallStatus": "ringing"}
        signature = RequestValidator("diagnostic-test-token").compute_signature("https://roomink.example" + endpoint, data)
        response = APIClient().post(endpoint, urlencode(data), content_type="application/x-www-form-urlencoded", HTTP_X_TWILIO_SIGNATURE=signature)
        self.assertEqual(response.status_code, 200)
        xml = ElementTree.fromstring(response.content)
        self.assertEqual(xml.find("Dial").attrib["action"], "https://roomink.example" + self.endpoint)
        self.assertEqual(xml.find("Dial/Sip").attrib["statusCallbackEvent"], "initiated ringing answered completed")
        self.assertEqual(CallLog.objects.get(contact_id="CAnew").diagnostic_events.count(), 2)
