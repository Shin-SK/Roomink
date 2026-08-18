from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from io import StringIO
from rest_framework.test import APIClient

from core.models import Cast, Customer, Store, StoreSlugAlias, UserProfile


User = get_user_model()


@override_settings(FRONTEND_URL="https://roomink.example", PUBLIC_BOOKING_ENABLED=True)
class StoreScopedCustomerUrlsTest(TestCase):
    def setUp(self):
        self.rs = Store.objects.create(name="アールズスパ", slug="scoped-rs-spa")
        self.tokyo = Store.objects.create(name="東京メンズエステ", slug="scoped-tokyo-mens-esthe")
        self.phone = "09012345678"
        self.rs_user = User.objects.create_user("rs-customer", password="rs-pass-123")
        self.tokyo_user = User.objects.create_user("tokyo-customer", password="tokyo-pass-123")
        self.rs_customer = Customer.objects.create(
            store=self.rs,
            user=self.rs_user,
            phone=self.phone,
            display_name="R顧客",
        )
        self.tokyo_customer = Customer.objects.create(
            store=self.tokyo,
            user=self.tokyo_user,
            phone=self.phone,
            display_name="東京顧客",
        )

    def test_public_booking_resolves_slug_without_exposing_other_store(self):
        Cast.objects.create(store=self.rs, name="Rキャスト")
        Cast.objects.create(store=self.tokyo, name="東京キャスト")

        response = APIClient().get(
            "/api/public/booking/options/",
            {"store_slug": "scoped-rs-spa"},
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["store"]["slug"], "scoped-rs-spa")
        self.assertEqual([item["name"] for item in response.data["casts"]], ["Rキャスト"])
        self.assertNotContains(response, "東京キャスト")

    def test_store_scoped_login_disambiguates_same_phone_without_leaking(self):
        rs_client = APIClient()
        rs_login = rs_client.post(
            "/api/cu/login/",
            {"store_slug": "scoped-rs-spa", "phone": self.phone, "password": "rs-pass-123"},
            format="json",
        )
        wrong_store = APIClient().post(
            "/api/cu/login/",
            {"store_slug": "scoped-tokyo-mens-esthe", "phone": self.phone, "password": "rs-pass-123"},
            format="json",
        )
        missing = APIClient().post(
            "/api/cu/login/",
            {"store_slug": "missing-store", "phone": self.phone, "password": "rs-pass-123"},
            format="json",
        )

        self.assertEqual(rs_login.status_code, 200, rs_login.data)
        self.assertEqual(rs_login.data["store_slug"], "scoped-rs-spa")
        self.assertEqual(wrong_store.status_code, 401)
        self.assertEqual(wrong_store.json(), missing.json())

    def test_customer_api_rejects_other_store_slug(self):
        client = APIClient()
        client.force_authenticate(self.rs_user)

        own = client.get("/api/cu/mypage/", {"store_slug": "scoped-rs-spa"})
        other = client.get("/api/cu/mypage/", {"store_slug": "scoped-tokyo-mens-esthe"})

        self.assertEqual(own.status_code, 200, own.data)
        self.assertEqual(other.status_code, 403, other.data)

    def test_manager_can_change_slug_and_old_slug_still_resolves(self):
        manager = User.objects.create_user("rs-manager", password="manager-pass")
        UserProfile.objects.create(user=manager, store=self.rs, role=UserProfile.Role.MANAGER)
        client = APIClient()
        client.force_authenticate(manager)

        response = client.patch(
            "/api/op/public-booking-settings/",
            {"store_slug": "rs-tokyo", "public_booking_notice": "案内"},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["public_booking_url"], "https://roomink.example/s/rs-tokyo/booking")
        self.assertTrue(StoreSlugAlias.objects.filter(store=self.rs, slug="scoped-rs-spa").exists())
        self.assertEqual(Store.resolve_slug("scoped-rs-spa").pk, self.rs.pk)
        old_url = APIClient().get("/api/public/booking/options/", {"store_slug": "scoped-rs-spa"})
        self.assertEqual(old_url.status_code, 200, old_url.data)
        self.assertEqual(old_url.data["store"]["slug"], "rs-tokyo")

    def test_staff_cannot_change_store_slug(self):
        staff = User.objects.create_user("rs-staff", password="staff-pass")
        UserProfile.objects.create(user=staff, store=self.rs, role=UserProfile.Role.STAFF)
        client = APIClient()
        client.force_authenticate(staff)

        response = client.patch(
            "/api/op/public-booking-settings/",
            {"store_slug": "hijacked", "public_booking_notice": ""},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.rs.refresh_from_db()
        self.assertEqual(self.rs.slug, "scoped-rs-spa")

    def test_store_manager_provisioning_is_scoped_and_refuses_duplicate_username(self):
        output = StringIO()
        call_command(
            "provision_store_manager",
            store_slug="scoped-rs-spa",
            username="new-rs-manager",
            email="manager@example.com",
            stdout=output,
        )

        user = User.objects.get(username="new-rs-manager")
        self.assertEqual(user.profile.store, self.rs)
        self.assertEqual(user.profile.role, UserProfile.Role.MANAGER)
        self.assertTrue(user.has_usable_password())
        self.assertIn("temporary_password=", output.getvalue())
        with self.assertRaises(CommandError):
            call_command(
                "provision_store_manager",
                store_slug="scoped-tokyo-mens-esthe",
                username="new-rs-manager",
            )
