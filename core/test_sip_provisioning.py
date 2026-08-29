import hashlib
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import urlparse

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Customer, SipProvisioningLink, SipReceptionDevice, Store, UserProfile


User = get_user_model()


@override_settings(
    FRONTEND_URL="https://roomink.example",
    TWILIO_ACCOUNT_SID="ACtest",
    TWILIO_AUTH_TOKEN="test-token",
    TWILIO_SIP_CREDENTIAL_LIST_SID="CLtest",
)
class SipProvisioningTest(TestCase):
    settings_path = "/api/op/sip-provisioning/settings/"
    devices_path = "/api/op/sip-reception-devices/"

    def setUp(self):
        self.store = Store.objects.create(name="QRテスト店舗", slug="qr-test")
        self.other_store = Store.objects.create(name="別店舗", slug="other-store")
        self.manager = self.create_user("sip_manager", self.store, UserProfile.Role.MANAGER)
        self.staff = self.create_user("sip_staff", self.store, UserProfile.Role.STAFF)
        self.cast = self.create_user("sip_cast", self.store, UserProfile.Role.CAST)
        self.customer = User.objects.create_user("sip_customer")
        Customer.objects.create(
            store=self.store,
            user=self.customer,
            phone="07000009999",
            display_name="SIPテスト顧客",
        )
        self.other_manager = self.create_user(
            "other_sip_manager", self.other_store, UserProfile.Role.MANAGER,
        )
        self.anonymous = APIClient()

    def create_user(self, username, store, role):
        user = User.objects.create_user(username)
        UserProfile.objects.create(user=user, store=store, role=role)
        return user

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def configure_store(self, client=None):
        client = client or self.client_for(self.manager)
        return client.patch(
            self.settings_path,
            {
                "sip_domain": "roomink-reception.sip.twilio.com",
            },
            format="json",
        )

    def create_device(self, label="受付iPhone 1"):
        self.configure_store()
        with patch(
            "core.views._create_twilio_sip_credential",
            return_value=f"CR{label.replace(' ', '')}",
        ):
            return self.client_for(self.manager).post(
                self.devices_path,
                {"label": label},
                format="json",
            )

    def test_manager_can_configure_own_store_domain(self):
        response = self.configure_store()

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["sip_domain"], "roomink-reception.sip.twilio.com")
        self.assertTrue(response.data["configured"])
        self.assertTrue(response.data["credential_api_configured"])

        self.store.refresh_from_db()
        self.assertEqual(self.store.sip_domain, "roomink-reception.sip.twilio.com")

        get_response = self.client_for(self.manager).get(self.settings_path)
        self.assertEqual(get_response.status_code, 200)
        self.assertNotIn("sip_password", get_response.data)
        self.assertNotIn("sip_username", get_response.data)

    def test_only_manager_can_read_or_change_sip_settings(self):
        for user in (self.staff, self.cast, self.customer):
            with self.subTest(user=user.username):
                client = self.client_for(user)
                self.assertEqual(client.get(self.settings_path).status_code, 403)
                self.assertEqual(
                    client.patch(
                        self.settings_path,
                        {"sip_username": "blocked"},
                        format="json",
                    ).status_code,
                    403,
                )
                self.assertEqual(client.get(self.devices_path).status_code, 403)
                self.assertEqual(
                    client.post(self.devices_path, {"label": "blocked"}, format="json").status_code,
                    403,
                )

        self.assertEqual(self.anonymous.get(self.settings_path).status_code, 403)
        self.assertEqual(self.anonymous.get(self.devices_path).status_code, 403)
        self.assertFalse(SipProvisioningLink.objects.exists())

    def test_settings_are_store_scoped(self):
        self.configure_store()

        response = self.client_for(self.other_manager).get(self.settings_path)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["configured"])
        self.assertEqual(response.data["sip_domain"], "")

    def test_invalid_domain_is_rejected_without_database_update(self):
        response = self.client_for(self.manager).patch(
            self.settings_path,
            {
                "sip_domain": "attacker.example.com",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.store.refresh_from_db()
        self.assertEqual(self.store.sip_domain, "")

    def test_manager_creates_unique_device_and_short_lived_groundwire_link(self):
        response = self.create_device()

        self.assertEqual(response.status_code, 201, response.data)
        provisioning_url = response.data["provisioning_url"]
        token = urlparse(provisioning_url).path.rstrip("/").split("/")[-1]
        link = SipProvisioningLink.objects.get()
        device = SipReceptionDevice.objects.get()
        self.assertEqual(link.device, device)
        self.assertEqual(device.label, "受付iPhone 1")
        self.assertTrue(device.sip_username.startswith(f"roomink-{self.store.pk}-"))
        self.assertNotIn(device.provisioning_password, str(response.data))
        self.assertEqual(link.token_hash, hashlib.sha256(token.encode()).hexdigest())
        self.assertNotEqual(link.token_hash, token)

        provisioned = self.anonymous.get(urlparse(provisioning_url).path)
        self.assertEqual(provisioned.status_code, 200)
        self.assertEqual(provisioned["Cache-Control"], "no-store")
        self.assertEqual(provisioned["Content-Type"], "text/html; charset=utf-8")
        self.assertEqual(provisioned["Referrer-Policy"], "no-referrer")
        body = provisioned.content.decode()
        self.assertIn("Groundwire受付設定", body)
        self.assertIn("受付iPhone 1", body)
        self.assertIn(device.sip_username, body)
        self.assertIn(device.provisioning_password, body)
        self.assertIn("roomink-reception.sip.twilio.com", body)
        self.assertIn("sip.tokyo.twilio.com", body)
        self.assertIn("tls (sip)", body)

        link.refresh_from_db()
        device.refresh_from_db()
        self.assertIsNotNone(link.used_at)
        self.assertIsNotNone(device.provisioned_at)
        self.assertEqual(device.provisioning_password, "")
        second = self.anonymous.get(urlparse(provisioning_url).path)
        self.assertEqual(second.status_code, 410)

    def test_expired_or_unknown_link_does_not_expose_configuration(self):
        response = self.create_device()
        path = urlparse(response.data["provisioning_url"]).path
        device = SipReceptionDevice.objects.get()
        SipProvisioningLink.objects.update(expires_at=timezone.now() - timedelta(seconds=1))

        expired = self.anonymous.get(path)
        unknown = self.anonymous.get("/api/provisioning/groundwire/not-a-real-token/")

        self.assertEqual(expired.status_code, 410)
        self.assertEqual(unknown.status_code, 404)
        self.assertNotIn(device.sip_username, expired.content.decode())
        self.assertNotIn(device.provisioning_password, expired.content.decode())

    def test_create_requires_domain_and_twilio_api_configuration(self):
        response = self.client_for(self.manager).post(
            self.devices_path,
            {"label": "受付iPhone"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(SipReceptionDevice.objects.exists())
        self.assertFalse(SipProvisioningLink.objects.exists())

        self.configure_store()
        with override_settings(TWILIO_SIP_CREDENTIAL_LIST_SID=""):
            missing_api = self.client_for(self.manager).post(
                self.devices_path,
                {"label": "受付iPhone"},
                format="json",
            )
        self.assertEqual(missing_api.status_code, 503)
        self.assertFalse(SipReceptionDevice.objects.exists())

    def test_twilio_create_failure_does_not_create_device(self):
        self.configure_store()
        with patch(
            "core.views._create_twilio_sip_credential",
            side_effect=RuntimeError("provider unavailable"),
        ):
            response = self.client_for(self.manager).post(
                self.devices_path,
                {"label": "受付iPhone"},
                format="json",
            )

        self.assertEqual(response.status_code, 502)
        self.assertFalse(SipReceptionDevice.objects.exists())
        self.assertFalse(SipProvisioningLink.objects.exists())

    def test_active_device_limit_is_ten(self):
        self.configure_store()
        for index in range(10):
            SipReceptionDevice.objects.create(
                store=self.store,
                label=f"端末{index + 1}",
                sip_username=f"device-{index + 1}",
                twilio_credential_sid=f"CR{index + 1}",
                is_active=True,
            )

        response = self.client_for(self.manager).post(
            self.devices_path,
            {"label": "11台目"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(SipReceptionDevice.objects.filter(store=self.store).count(), 10)

    def test_other_store_cannot_reissue_or_disable_device(self):
        response = self.create_device()
        device_id = response.data["device"]["id"]
        other_client = self.client_for(self.other_manager)

        reissue = other_client.post(
            f"{self.devices_path}{device_id}/provision/",
            {},
            format="json",
        )
        disable = other_client.post(
            f"{self.devices_path}{device_id}/deactivate/",
            {},
            format="json",
        )

        self.assertEqual(reissue.status_code, 404)
        self.assertEqual(disable.status_code, 404)
        self.assertTrue(SipReceptionDevice.objects.get(pk=device_id).is_active)

    def test_reissue_rotates_only_selected_device_password(self):
        response = self.create_device()
        device = SipReceptionDevice.objects.get()
        previous_password = device.provisioning_password

        with patch("core.views._update_twilio_sip_credential") as update_mock:
            reissued = self.client_for(self.manager).post(
                f"{self.devices_path}{device.pk}/provision/",
                {},
                format="json",
            )

        self.assertEqual(reissued.status_code, 201, reissued.data)
        device.refresh_from_db()
        self.assertNotEqual(device.provisioning_password, previous_password)
        update_mock.assert_called_once_with(
            device.twilio_credential_sid,
            device.provisioning_password,
        )

    def test_deactivate_revokes_only_selected_device(self):
        first_response = self.create_device("受付iPhone 1")
        second_response = self.create_device("受付iPhone 2")
        first = SipReceptionDevice.objects.get(pk=first_response.data["device"]["id"])
        second = SipReceptionDevice.objects.get(pk=second_response.data["device"]["id"])

        with patch("core.views._delete_twilio_sip_credential", return_value=True) as delete_mock:
            response = self.client_for(self.manager).post(
                f"{self.devices_path}{first.pk}/deactivate/",
                {},
                format="json",
            )

        self.assertEqual(response.status_code, 200, response.data)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_active)
        self.assertEqual(first.twilio_credential_sid, "")
        self.assertTrue(second.is_active)
        delete_mock.assert_called_once()

    def test_local_deactivation_is_fail_closed_when_twilio_delete_fails(self):
        response = self.create_device()
        device = SipReceptionDevice.objects.get()

        with patch(
            "core.views._delete_twilio_sip_credential",
            side_effect=RuntimeError("provider unavailable"),
        ):
            disabled = self.client_for(self.manager).post(
                f"{self.devices_path}{device.pk}/deactivate/",
                {},
                format="json",
            )

        self.assertEqual(disabled.status_code, 502)
        device.refresh_from_db()
        self.assertFalse(device.is_active)
        self.assertTrue(device.twilio_credential_sid)
        self.assertTrue(disabled.data["device"]["revocation_pending"])
