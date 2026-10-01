import os
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from core.models import Customer, Order, Store, UserProfile
from core.services.public_booking import generate_public_booking_code


class StagingEnvironmentTest(TestCase):
    def test_seed_command_refuses_to_run_outside_staging(self):
        with patch.dict(os.environ, {"DJANGO_ENV": "production"}, clear=False):
            with self.assertRaisesMessage(CommandError, "DJANGO_ENV=staging"):
                call_command("seed_staging_demo")

    def test_seed_creates_only_explicit_demo_data(self):
        env = {
            "DJANGO_ENV": "staging",
            "SMS_DUMMY_MODE": "1",
            "STAGING_MANAGER_PASSWORD": "manager-test-password",
            "STAGING_CAST_PASSWORD": "cast-test-password",
        }
        with patch.dict(os.environ, env, clear=False):
            call_command("seed_staging_demo", stdout=StringIO())

        store = Store.objects.get(slug="flagship-staging")
        self.assertEqual(store.public_booking_notification_email, "")
        self.assertEqual(store.guest_contact_phone, "")
        self.assertEqual(store.sip_username, "")
        self.assertTrue(store.sms_billing_exempt)
        self.assertEqual(store.rooms.count(), 3)
        self.assertEqual(store.casts.count(), 3)
        self.assertEqual(store.courses.count(), 4)
        self.assertEqual(store.shift_assignments.count(), 21)
        self.assertEqual(Customer.objects.filter(store=store).count(), 3)
        self.assertEqual(Order.objects.filter(store=store).count(), 3)
        self.assertFalse(
            Customer.objects.filter(store=store).exclude(display_name__startswith="テスト").exists()
        )
        self.assertTrue(
            UserProfile.objects.filter(
                store=store,
                user__username="staging_manager",
                role=UserProfile.Role.MANAGER,
            ).exists()
        )

    @override_settings(PUBLIC_BOOKING_TEST_CODE="654321")
    def test_staging_public_booking_code_can_be_fixed_for_manual_check(self):
        self.assertEqual(generate_public_booking_code(), "654321")
