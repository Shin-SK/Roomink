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
    "TWILIO_BYOC_TRUNK_SID": "BY" + "3" * 32,
    "TWILIO_BYOC_TERMINATION_DOMAIN_SID": "SD" + "4" * 32,
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
            sip_domain="roomink-reception.sip.twilio.com",
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

    def test_local_readiness_passes_without_printing_secrets(self):
        stdout = StringIO()

        call_command("check_voice_readiness", store_id=self.store.id, stdout=stdout)

        self.assertIn("VOICE READY (local)", stdout.getvalue())
        self.assertNotIn("test-auth-token", stdout.getvalue())

    @override_settings(TWILIO_BYOC_TRUNK_SID="")
    def test_missing_carrier_configuration_fails_closed(self):
        with self.assertRaises(CommandError):
            call_command(
                "check_voice_readiness",
                store_id=self.store.id,
                stdout=StringIO(),
                stderr=StringIO(),
            )

    def test_live_readiness_reads_twilio_and_verifies_routes(self):
        trunk = MagicMock(
            voice_url="https://api.roomink.net/api/webhook/twilio/voice/",
            voice_method="POST",
            status_callback_url="https://api.roomink.net/api/webhook/twilio/status/",
            status_callback_method="POST",
        )
        domain = MagicMock(
            byoc_trunk_sid=READY_SETTINGS["TWILIO_BYOC_TRUNK_SID"],
            domain_name=self.store.sip_domain,
            auth_type="IP_ACL",
            sip_registration=True,
            secure=False,
        )
        domain.credential_list_mappings.list.return_value = []
        domain.ip_access_control_list_mappings.list.return_value = [MagicMock(
            ip_access_control_list_sid=READY_SETTINGS["TWILIO_BYOC_IP_ACCESS_CONTROL_LIST_SID"],
        )]
        domain.auth.registrations.credential_list_mappings.list.return_value = [MagicMock(
            credential_list_sid=READY_SETTINGS["TWILIO_SIP_CREDENTIAL_LIST_SID"],
        )]
        sms_number = MagicMock(capabilities={"sms": True})
        client = MagicMock()
        client.voice.v1.byoc_trunks.return_value.fetch.return_value = trunk
        client.api.v2010.account.sip.domains.return_value.fetch.return_value = domain
        client.incoming_phone_numbers.list.return_value = [sms_number]
        stdout = StringIO()

        with patch("twilio.rest.Client", return_value=client):
            call_command(
                "check_voice_readiness",
                store_id=self.store.id,
                live=True,
                stdout=stdout,
            )

        self.assertIn("VOICE READY (live)", stdout.getvalue())

    def test_live_readiness_rejects_a_different_termination_domain(self):
        trunk = MagicMock(
            voice_url="https://api.roomink.net/api/webhook/twilio/voice/",
            voice_method="POST",
            status_callback_url="https://api.roomink.net/api/webhook/twilio/status/",
            status_callback_method="POST",
        )
        domain = MagicMock(
            byoc_trunk_sid=READY_SETTINGS["TWILIO_BYOC_TRUNK_SID"],
            domain_name="roomink-clocall.sip.twilio.com",
            auth_type="IP_ACL",
            sip_registration=False,
            secure=False,
        )
        domain.credential_list_mappings.list.return_value = []
        domain.ip_access_control_list_mappings.list.return_value = [MagicMock(
            ip_access_control_list_sid=READY_SETTINGS["TWILIO_BYOC_IP_ACCESS_CONTROL_LIST_SID"],
        )]
        domain.auth.registrations.credential_list_mappings.list.return_value = []
        client = MagicMock()
        client.voice.v1.byoc_trunks.return_value.fetch.return_value = trunk
        client.api.v2010.account.sip.domains.return_value.fetch.return_value = domain
        client.incoming_phone_numbers.list.return_value = [
            MagicMock(capabilities={"sms": True}),
        ]

        with patch("twilio.rest.Client", return_value=client), self.assertRaises(CommandError):
            call_command(
                "check_voice_readiness",
                store_id=self.store.id,
                live=True,
                stdout=StringIO(),
                stderr=StringIO(),
            )

    def test_live_readiness_rejects_call_credentials_on_submitted_domain(self):
        trunk = MagicMock(
            voice_url="https://api.roomink.net/api/webhook/twilio/voice/",
            voice_method="POST",
            status_callback_url="https://api.roomink.net/api/webhook/twilio/status/",
            status_callback_method="POST",
        )
        domain = MagicMock(
            byoc_trunk_sid=READY_SETTINGS["TWILIO_BYOC_TRUNK_SID"],
            domain_name=self.store.sip_domain,
            auth_type="IP_ACL,CREDENTIAL_LIST",
            sip_registration=True,
            secure=False,
        )
        domain.credential_list_mappings.list.return_value = [MagicMock(
            credential_list_sid="CL" + "8" * 32,
        )]
        domain.ip_access_control_list_mappings.list.return_value = [MagicMock(
            ip_access_control_list_sid=READY_SETTINGS["TWILIO_BYOC_IP_ACCESS_CONTROL_LIST_SID"],
        )]
        domain.auth.registrations.credential_list_mappings.list.return_value = [MagicMock(
            credential_list_sid=READY_SETTINGS["TWILIO_SIP_CREDENTIAL_LIST_SID"],
        )]
        client = MagicMock()
        client.voice.v1.byoc_trunks.return_value.fetch.return_value = trunk
        client.api.v2010.account.sip.domains.return_value.fetch.return_value = domain
        client.incoming_phone_numbers.list.return_value = [
            MagicMock(capabilities={"sms": True}),
        ]
        with patch("twilio.rest.Client", return_value=client), self.assertRaises(CommandError):
            call_command(
                "check_voice_readiness",
                store_id=self.store.id,
                live=True,
                stdout=StringIO(),
                stderr=StringIO(),
            )

    def test_live_readiness_rejects_secure_media_enforcement_for_udp_carrier(self):
        trunk = MagicMock(
            voice_url="https://api.roomink.net/api/webhook/twilio/voice/",
            voice_method="POST",
            status_callback_url="https://api.roomink.net/api/webhook/twilio/status/",
            status_callback_method="POST",
        )
        domain = MagicMock(
            byoc_trunk_sid=READY_SETTINGS["TWILIO_BYOC_TRUNK_SID"],
            domain_name=self.store.sip_domain,
            auth_type="IP_ACL",
            sip_registration=True,
            secure=True,
        )
        domain.credential_list_mappings.list.return_value = []
        domain.ip_access_control_list_mappings.list.return_value = [MagicMock(
            ip_access_control_list_sid=READY_SETTINGS["TWILIO_BYOC_IP_ACCESS_CONTROL_LIST_SID"],
        )]
        domain.auth.registrations.credential_list_mappings.list.return_value = [MagicMock(
            credential_list_sid=READY_SETTINGS["TWILIO_SIP_CREDENTIAL_LIST_SID"],
        )]
        client = MagicMock()
        client.voice.v1.byoc_trunks.return_value.fetch.return_value = trunk
        client.api.v2010.account.sip.domains.return_value.fetch.return_value = domain
        client.incoming_phone_numbers.list.return_value = [
            MagicMock(capabilities={"sms": True}),
        ]

        with patch("twilio.rest.Client", return_value=client), self.assertRaises(CommandError):
            call_command(
                "check_voice_readiness",
                store_id=self.store.id,
                live=True,
                stdout=StringIO(),
                stderr=StringIO(),
            )

    @override_settings(
        TWILIO_BYOC_CREDENTIAL_LIST_SID="",
        TWILIO_BYOC_IP_ACCESS_CONTROL_LIST_SID="AL" + "7" * 32,
    )
    def test_live_readiness_accepts_shared_domain_with_separate_registration_auth(self):
        trunk = MagicMock(
            voice_url="https://api.roomink.net/api/webhook/twilio/voice/",
            voice_method="POST",
            status_callback_url="https://api.roomink.net/api/webhook/twilio/status/",
            status_callback_method="POST",
        )
        domain = MagicMock(
            byoc_trunk_sid=READY_SETTINGS["TWILIO_BYOC_TRUNK_SID"],
            domain_name=self.store.sip_domain,
            auth_type="IP_ACL",
            sip_registration=True,
            secure=False,
        )
        domain.credential_list_mappings.list.return_value = []
        domain.ip_access_control_list_mappings.list.return_value = [MagicMock(
            ip_access_control_list_sid="AL" + "7" * 32,
        )]
        domain.auth.registrations.credential_list_mappings.list.return_value = [MagicMock(
            credential_list_sid=READY_SETTINGS["TWILIO_SIP_CREDENTIAL_LIST_SID"],
        )]
        client = MagicMock()
        client.voice.v1.byoc_trunks.return_value.fetch.return_value = trunk
        client.api.v2010.account.sip.domains.return_value.fetch.return_value = domain
        client.incoming_phone_numbers.list.return_value = [
            MagicMock(capabilities={"sms": True}),
        ]
        stdout = StringIO()

        with patch("twilio.rest.Client", return_value=client):
            call_command(
                "check_voice_readiness",
                store_id=self.store.id,
                live=True,
                stdout=stdout,
            )

        self.assertIn("VOICE READY (live)", stdout.getvalue())

    def test_live_readiness_accepts_real_twilio_mapping_shape(self):
        trunk = MagicMock(
            voice_url="https://api.roomink.net/api/webhook/twilio/voice/",
            voice_method="POST",
            status_callback_url="https://api.roomink.net/api/webhook/twilio/status/",
            status_callback_method="POST",
        )
        domain = MagicMock(
            byoc_trunk_sid=READY_SETTINGS["TWILIO_BYOC_TRUNK_SID"],
            domain_name=self.store.sip_domain,
            auth_type="IP_ACL",
            sip_registration=True,
            secure=False,
        )
        domain.credential_list_mappings.list.return_value = []
        domain.ip_access_control_list_mappings.list.return_value = [MagicMock(
            spec=["sid"],
            sid="AL" + "7" * 32,
        )]
        domain.auth.registrations.credential_list_mappings.list.return_value = [MagicMock(
            spec=["sid"],
            sid=READY_SETTINGS["TWILIO_SIP_CREDENTIAL_LIST_SID"],
        )]
        client = MagicMock()
        client.voice.v1.byoc_trunks.return_value.fetch.return_value = trunk
        client.api.v2010.account.sip.domains.return_value.fetch.return_value = domain
        client.incoming_phone_numbers.list.return_value = [
            MagicMock(capabilities={"sms": True}),
        ]
        stdout = StringIO()

        with patch("twilio.rest.Client", return_value=client):
            call_command(
                "check_voice_readiness",
                store_id=self.store.id,
                live=True,
                stdout=stdout,
            )

        self.assertIn("VOICE READY (live)", stdout.getvalue())

    @override_settings(
        TWILIO_BYOC_CREDENTIAL_LIST_SID=READY_SETTINGS["TWILIO_SIP_CREDENTIAL_LIST_SID"],
    )
    def test_carrier_cannot_share_reception_device_credentials(self):
        with self.assertRaises(CommandError):
            call_command(
                "check_voice_readiness",
                store_id=self.store.id,
                stdout=StringIO(),
                stderr=StringIO(),
            )
