import hashlib
from datetime import timedelta
from urllib.parse import urlparse
from xml.etree import ElementTree

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Customer, SipProvisioningLink, Store, UserProfile


User = get_user_model()


@override_settings(FRONTEND_URL="https://roomink.example")
class SipProvisioningTest(TestCase):
    settings_path = "/api/op/sip-provisioning/settings/"
    issue_path = "/api/op/sip-provisioning/issue/"

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
                "sip_username": "roomink-reception",
                "sip_password": "strong-test-password-123",
                "sip_domain": "roomink-reception.sip.twilio.com",
            },
            format="json",
        )

    def issue_link(self):
        self.configure_store()
        return self.client_for(self.manager).post(self.issue_path, {}, format="json")

    def test_manager_can_configure_own_store_without_password_disclosure(self):
        response = self.configure_store()

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["sip_username"], "roomink-reception")
        self.assertEqual(response.data["sip_domain"], "roomink-reception.sip.twilio.com")
        self.assertTrue(response.data["configured"])
        self.assertNotIn("sip_password", response.data)

        self.store.refresh_from_db()
        self.assertEqual(self.store.sip_username, "roomink-reception")
        self.assertEqual(self.store.sip_password, "strong-test-password-123")

        get_response = self.client_for(self.manager).get(self.settings_path)
        self.assertEqual(get_response.status_code, 200)
        self.assertNotIn("sip_password", get_response.data)

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
                self.assertEqual(client.post(self.issue_path).status_code, 403)

        self.assertEqual(self.anonymous.get(self.settings_path).status_code, 403)
        self.assertEqual(self.anonymous.post(self.issue_path).status_code, 403)
        self.assertFalse(SipProvisioningLink.objects.exists())

    def test_blank_password_is_not_required_when_existing_password_is_kept(self):
        self.configure_store()

        response = self.client_for(self.manager).patch(
            self.settings_path,
            {
                "sip_username": "roomink-reception-updated",
                "sip_domain": "roomink-reception.sip.twilio.com",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.store.refresh_from_db()
        self.assertEqual(self.store.sip_username, "roomink-reception-updated")
        self.assertEqual(self.store.sip_password, "strong-test-password-123")

    def test_settings_are_store_scoped(self):
        self.configure_store()

        response = self.client_for(self.other_manager).get(self.settings_path)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["configured"])
        self.assertEqual(response.data["sip_username"], "")

    def test_invalid_domain_is_rejected_without_database_update(self):
        response = self.client_for(self.manager).patch(
            self.settings_path,
            {
                "sip_username": "roomink-reception",
                "sip_password": "strong-test-password-123",
                "sip_domain": "attacker.example.com",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.store.refresh_from_db()
        self.assertEqual(self.store.sip_username, "")
        self.assertEqual(self.store.sip_password, "")
        self.assertEqual(self.store.sip_domain, "")

    def test_short_lived_link_provisions_linphone_once(self):
        response = self.issue_link()

        self.assertEqual(response.status_code, 201, response.data)
        self.assertNotIn("strong-test-password-123", str(response.data))
        provisioning_url = response.data["provisioning_url"]
        token = urlparse(provisioning_url).path.rstrip("/").split("/")[-1]
        link = SipProvisioningLink.objects.get()
        self.assertEqual(link.token_hash, hashlib.sha256(token.encode()).hexdigest())
        self.assertNotEqual(link.token_hash, token)

        provisioned = self.anonymous.get(urlparse(provisioning_url).path)
        self.assertEqual(provisioned.status_code, 200)
        self.assertEqual(provisioned["Cache-Control"], "no-store")
        self.assertEqual(provisioned["Content-Type"], "application/xml")
        root = ElementTree.fromstring(provisioned.content)
        namespace = {"lp": "http://www.linphone.org/xsds/lpconfig.xsd"}
        entries = {
            entry.attrib["name"]: entry.text
            for section in root.findall("lp:section", namespace)
            for entry in section.findall("lp:entry", namespace)
        }
        self.assertEqual(entries["username"], "roomink-reception")
        self.assertEqual(entries["passwd"], "strong-test-password-123")
        self.assertIn("roomink-reception.sip.twilio.com", entries["reg_proxy"])
        self.assertIn("sip.tokyo.twilio.com", entries["reg_route"])
        self.assertIn("transport=tls", entries["reg_proxy"])

        link.refresh_from_db()
        self.assertIsNotNone(link.used_at)
        second = self.anonymous.get(urlparse(provisioning_url).path)
        self.assertEqual(second.status_code, 410)

    def test_expired_or_unknown_link_does_not_expose_configuration(self):
        response = self.issue_link()
        path = urlparse(response.data["provisioning_url"]).path
        SipProvisioningLink.objects.update(expires_at=timezone.now() - timedelta(seconds=1))

        expired = self.anonymous.get(path)
        unknown = self.anonymous.get("/api/provisioning/linphone/not-a-real-token/")

        self.assertEqual(expired.status_code, 410)
        self.assertEqual(unknown.status_code, 404)
        self.assertNotIn("roomink-reception", expired.content.decode())
        self.assertNotIn("strong-test-password-123", expired.content.decode())

    def test_issue_requires_complete_configuration(self):
        response = self.client_for(self.manager).post(self.issue_path, {}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertFalse(SipProvisioningLink.objects.exists())
