from importlib import import_module
from types import SimpleNamespace

from django.test import TestCase

from core.models import Store


migration = import_module("core.migrations.0061_seed_store_card_payment_urls")


class StoreCardPaymentUrlMigrationTests(TestCase):
    def setUp(self):
        self.apps = SimpleNamespace(
            get_model=lambda app_label, model_name: Store,
        )
        self.tokyo, _ = Store.objects.update_or_create(
            slug="tokyo-mens-esthe",
            defaults={
                "name": "東京メンズエステ",
                "card_payment_url": "",
            },
        )
        self.rs_spa, _ = Store.objects.update_or_create(
            slug="rs-spa",
            defaults={
                "name": "アールズスパ",
                "card_payment_url": "",
            },
        )
        self.other = Store.objects.create(
            name="他店舗",
            slug="other-store",
            card_payment_url="https://payment.example/other",
        )

    def test_forward_sets_only_the_two_store_urls(self):
        migration.set_card_payment_urls(self.apps, None)

        self.tokyo.refresh_from_db()
        self.rs_spa.refresh_from_db()
        self.other.refresh_from_db()
        self.assertEqual(
            self.tokyo.card_payment_url,
            "https://pay2.star-pay.jp/site/smt/shop.php?payc=A8496",
        )
        self.assertEqual(
            self.rs_spa.card_payment_url,
            "https://pay2.star-pay.jp/site/smt/shop.php?payc=A20254",
        )
        self.assertEqual(
            self.other.card_payment_url,
            "https://payment.example/other",
        )

    def test_reverse_preserves_a_value_changed_after_migration(self):
        migration.set_card_payment_urls(self.apps, None)
        Store.objects.filter(pk=self.tokyo.pk).update(
            card_payment_url="https://payment.example/replaced",
        )

        migration.clear_seeded_card_payment_urls(self.apps, None)

        self.tokyo.refresh_from_db()
        self.rs_spa.refresh_from_db()
        self.assertEqual(
            self.tokyo.card_payment_url,
            "https://payment.example/replaced",
        )
        self.assertEqual(self.rs_spa.card_payment_url, "")
