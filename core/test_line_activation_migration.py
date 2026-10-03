from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class LineActivationMigrationTest(TransactionTestCase):
    migrate_from = [("core", "0073_public_booking_notifications")]
    migrate_to = [("core", "0074_store_line_activation")]

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        Store = old_apps.get_model("core", "Store")
        Store.objects.create(
            name="既存稼働店",
            slug="existing-line-store",
            line_is_enabled=True,
            line_webhook_token="existing-webhook-token",
        )
        Store.objects.create(
            name="フラッグシップ",
            slug="flagship",
            line_is_enabled=True,
            line_webhook_token="flagship-webhook-token",
        )
        Store.objects.create(
            name="未接続店",
            slug="disabled-line-store",
            line_is_enabled=False,
            line_webhook_token="disabled-webhook-token",
        )

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        self.apps = executor.loader.project_state(self.migrate_to).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_existing_stores_keep_their_state_and_flagship_waits_for_start(self):
        Store = self.apps.get_model("core", "Store")
        existing = Store.objects.get(slug="existing-line-store")
        flagship = Store.objects.get(slug="flagship")
        disabled = Store.objects.get(slug="disabled-line-store")

        self.assertIsNotNone(existing.line_setup_completed_at)
        self.assertIsNotNone(existing.line_started_at)
        self.assertIsNotNone(flagship.line_setup_completed_at)
        self.assertIsNone(flagship.line_started_at)
        self.assertIsNone(disabled.line_setup_completed_at)
        self.assertIsNone(disabled.line_started_at)
