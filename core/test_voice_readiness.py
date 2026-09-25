from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import SipReceptionDevice, Store, StorePhoneNumber


READY_SETTINGS = {
    "TWILIO_ACCOUNT_SID": "AC" + "1" * 32,
    "TWILIO_AUTH_TOKEN": "test-auth-token",
    "TWILIO_FROM_PHONE": "+815012345678",
    "TWILIO_SIP_CREDENTIAL_LIST_SID": "CL" + "2" * 32,
    "TWILIO_SIP_REGISTRATION_DOMAIN_SID": "SD" + "6" * 32,
    "TWILIO_BYOC_TRUNK_SID": "BY" + "3" * 32,
    "TWILIO_BYOC_TERMINATION_DOMAIN_SID": "SD" + "4" * 32,
    "TWILIO_BYOC_TERMINATION_DOMAIN_NAME": "roomink-reception.sip.twilio.com",
    "TWILIO_BYOC_CREDENTIAL_LIST_SID": "",
    "TWILIO_BYOC_IP_ACCESS_CONTROL_LIST_SID": "AL" + "7" * 32,
    "TWILIO_WEBHOOK_PUBLIC_BASE_URL": "https://api.roomink.net",
    "TWILIO_WEBHOOK_ALLOW_UNSIGNED": False,
}


@override_settings(**READY_SETTINGS)
class VoiceReadinessCommandTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(
            name="音声開通テスト店",
            sip_domain="roomink-devices.sip.twilio.com",
        )
        StorePhoneNumber.objects.create(
            store=self.store,
            phone="05012345678",
            is_active=True,
        )
        SipReceptionDevice.objects.create(
            store=self.store,
            label="受付iPhone",
            sip_username="roomink-test-device",
            twilio_credential_sid="CR" + "5" * 32,
            provisioned_at=timezone.now(),
        )

    def _twilio_client(self):
        trunk = MagicMock(
            voice_url="https://api.roomink.net/api/webhook/twilio/voice/",
            voice_method="POST",
            status_callback_url="https://api.roomink.net/api/webhook/twilio/status/",
            status_callback_method="POST",
        )
        termination = MagicMock(
            byoc_trunk_sid=READY_SETTINGS["TWILIO_BYOC_TRUNK_SID"],
            domain_name=READY_SETTINGS["TWILIO_BYOC_TERMINATION_DOMAIN_NAME"],
            auth_type="IP_ACL",
            sip_registration=False,
            secure=False,
        )
        termination.credential_list_mappings.list.return_value = []
        termination.ip_access_control_list_mappings.list.return_value = [MagicMock(
            ip_access_control_list_sid=READY_SETTINGS["TWILIO_BYOC_IP_ACCESS_CONTROL_LIST_SID"],
        )]

        registration = MagicMock(
            byoc_trunk_sid=None,
            domain_name=self.store.sip_domain,
            auth_type="CREDENTIAL_LIST",
            sip_registration=True,
            secure=False,
        )
        credential_mapping = MagicMock(
            credential_list_sid=READY_SETTINGS["TWILIO_SIP_CREDENTIAL_LIST_SID"],
        )
        registration.credential_list_mappings.list.return_value = [credential_mapping]
        registration.auth.registrations.credential_list_mappings.list.return_value = [
            credential_mapping,
        ]

        domains = {
            READY_SETTINGS["TWILIO_BYOC_TERMINATION_DOMAIN_SID"]: termination,
            READY_SETTINGS["TWILIO_SIP_REGISTRATION_DOMAIN_SID"]: registration,
        }
        client = MagicMock()
        client.voice.v1.byoc_trunks.return_value.fetch.return_value = trunk
        client.api.v2010.account.sip.domains.side_effect = (
            lambda sid: MagicMock(fetch=MagicMock(return_value=domains[sid]))
        )
        client.incoming_phone_numbers.list.return_value = [
            MagicMock(capabilities={"sms": True}),
        ]
        return client, termination, registration

    def _run_live(self, client, stdout=None, stderr=None):
        with patch("twilio.rest.Client", return_value=client):
            call_command(
                "check_voice_readiness",
                store_id=self.store.id,
                live=True,
                stdout=stdout or StringIO(),
                stderr=stderr or StringIO(),
            )

    def test_local_readiness_passes_without_printing_secrets(self):
        stdout = StringIO()
        call_command("check_voice_readiness", store_id=self.store.id, stdout=stdout)
        self.assertIn("VOICE READY (local)", stdout.getvalue())
        self.assertNotIn("test-auth-token", stdout.getvalue())

    @override_settings(TWILIO_SIP_REGISTRATION_DOMAIN_SID="")
    def test_missing_registration_domain_configuration_fails_closed(self):
        with self.assertRaises(CommandError):
            call_command(
                "check_voice_readiness",
                store_id=self.store.id,
                stdout=StringIO(),
                stderr=StringIO(),
            )

    def test_live_readiness_accepts_separate_carrier_and_device_domains(self):
        client, _, _ = self._twilio_client()
        stdout = StringIO()
        self._run_live(client, stdout=stdout)
        self.assertIn("VOICE READY (live)", stdout.getvalue())

    def test_live_readiness_rejects_shared_carrier_and_device_domain(self):
        self.store.sip_domain = READY_SETTINGS["TWILIO_BYOC_TERMINATION_DOMAIN_NAME"]
        self.store.save(update_fields=["sip_domain"])
        client, _, registration = self._twilio_client()
        registration.domain_name = READY_SETTINGS["TWILIO_BYOC_TERMINATION_DOMAIN_NAME"]
        with self.assertRaises(CommandError):
            self._run_live(client)

    def test_live_readiness_rejects_wrong_submitted_carrier_domain(self):
        client, termination, _ = self._twilio_client()
        termination.domain_name = "roomink-other.sip.twilio.com"
        with self.assertRaises(CommandError):
            self._run_live(client)

    def test_live_readiness_rejects_call_credentials_on_carrier_domain(self):
        client, termination, _ = self._twilio_client()
        termination.auth_type = "IP_ACL,CREDENTIAL_LIST"
        termination.credential_list_mappings.list.return_value = [MagicMock(
            credential_list_sid=READY_SETTINGS["TWILIO_SIP_CREDENTIAL_LIST_SID"],
        )]
        with self.assertRaises(CommandError):
            self._run_live(client)

    def test_live_readiness_rejects_byoc_link_on_device_domain(self):
        client, _, registration = self._twilio_client()
        registration.byoc_trunk_sid = READY_SETTINGS["TWILIO_BYOC_TRUNK_SID"]
        with self.assertRaises(CommandError):
            self._run_live(client)

    def test_live_readiness_requires_registration_and_call_credentials(self):
        client, _, registration = self._twilio_client()
        registration.auth.registrations.credential_list_mappings.list.return_value = []
        registration.credential_list_mappings.list.return_value = []
        with self.assertRaises(CommandError):
            self._run_live(client)

    def test_live_readiness_accepts_real_twilio_mapping_shape(self):
        client, termination, registration = self._twilio_client()
        termination.ip_access_control_list_mappings.list.return_value = [MagicMock(
            spec=["sid"],
            sid=READY_SETTINGS["TWILIO_BYOC_IP_ACCESS_CONTROL_LIST_SID"],
        )]
        registration_mapping = MagicMock(
            spec=["sid"],
            sid=READY_SETTINGS["TWILIO_SIP_CREDENTIAL_LIST_SID"],
        )
        registration.credential_list_mappings.list.return_value = [registration_mapping]
        registration.auth.registrations.credential_list_mappings.list.return_value = [
            registration_mapping,
        ]
        stdout = StringIO()
        self._run_live(client, stdout=stdout)
        self.assertIn("VOICE READY (live)", stdout.getvalue())
