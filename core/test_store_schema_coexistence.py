"""Writing with the pre-Work Store model against the newer schema.

These tests run only in Django's disposable test database. They never connect
to staging or production and never reverse the shared database's migrations.
"""
import uuid

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from .models import Store, WorkDevice, WorkDeviceCredential, WorkDeviceStore
from .work_device_views import _issue_credential


class LegacyStoreWriteCompatibilityTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        executor = MigrationExecutor(connection)
        cls.LegacyStore = executor.loader.project_state(
            [("core", "0092_store_shift_request_start_hour")]
        ).apps.get_model("core", "Store")

    def test_legacy_insert_uses_database_default(self):
        self.assertNotIn("voice_receiver", {f.name for f in self.LegacyStore._meta.fields})
        legacy = self.LegacyStore.objects.create(name="Legacy registration")
        self.assertEqual(Store.objects.get(pk=legacy.pk).voice_receiver, "groundwire")

    def test_legacy_bulk_insert_uses_database_default(self):
        self.LegacyStore.objects.bulk_create([
            self.LegacyStore(name="Legacy batch A", slug="legacy-a", line_webhook_token=uuid.uuid4().hex),
            self.LegacyStore(name="Legacy batch B", slug="legacy-b", line_webhook_token=uuid.uuid4().hex),
        ])
        self.assertEqual(list(Store.objects.filter(slug__in=["legacy-a", "legacy-b"]).order_by("name").values_list("voice_receiver", flat=True)),
                         ["groundwire", "groundwire"])

    def test_legacy_update_preserves_existing_work_selection(self):
        store = Store.objects.create(name="Existing Work store", voice_receiver="work")
        legacy = self.LegacyStore.objects.get(pk=store.pk)
        legacy.name = "Renamed by ordinary Roomink"
        legacy.save()
        store.refresh_from_db()
        self.assertEqual(store.name, legacy.name)
        self.assertEqual(store.voice_receiver, "work")

    def test_explicit_selection_remains_explicit(self):
        store = Store.objects.create(name="Explicit Work", voice_receiver="work")
        self.assertEqual(Store.objects.get(pk=store.pk).voice_receiver, "work")

    def test_work_and_line_migrations_have_one_leaf(self):
        loader = MigrationExecutor(connection).loader
        self.assertEqual(loader.graph.leaf_nodes("core"),
                         [("core", "0095_store_voice_receiver_db_default")])
        ancestors = loader.graph.forwards_plan(("core", "0094_merge_work_line"))
        self.assertIn(("core", "0093_line_registration_session"), ancestors)
        self.assertIn(("core", "0093_store_voice_receiver_voicerouteevent"), ancestors)


class StoreMigrationPathTest(TransactionTestCase):
    """Only the disposable test DB is reset to exercise both migration paths."""
    latest = ("core", "0095_store_voice_receiver_db_default")

    def setUp(self):
        MigrationExecutor(connection).migrate([("core", "0092_store_shift_request_start_hour")])

    def tearDown(self):
        try:
            MigrationExecutor(connection).migrate([self.latest])
        finally:
            super().tearDown()

    def test_work_first_upgrade_preserves_receiver_and_credentials(self):
        executor = MigrationExecutor(connection)
        work = ("core", "0093_store_voice_receiver_voicerouteevent")
        executor.migrate([work])
        old_store = executor.loader.project_state([work]).apps.get_model("core", "Store")
        store = old_store.objects.create(name="Preserved Work", slug="preserved-work",
                                        line_webhook_token=uuid.uuid4().hex, voice_receiver="work")
        device = WorkDevice.objects.create(device_key=uuid.uuid4(), label="Preserved phone", status="active")
        subscription = WorkDeviceStore.objects.create(device=device, store_id=store.pk, is_receiving=True)
        _issue_credential(device)
        credential = WorkDeviceCredential.objects.get(device=device)
        expires = credential.expires_at
        MigrationExecutor(connection).migrate([self.latest])
        self.assertEqual(Store.objects.get(pk=store.pk).voice_receiver, "work")
        self.assertEqual(WorkDevice.objects.get(pk=device.pk).status, "active")
        self.assertTrue(WorkDeviceStore.objects.get(pk=subscription.pk).is_receiving)
        credential.refresh_from_db()
        self.assertIsNone(credential.revoked_at)
        self.assertEqual(credential.expires_at, expires)
        executor = MigrationExecutor(connection)
        self.assertEqual(executor.migration_plan([self.latest]), [])

    def test_ordinary_first_upgrade_still_allows_legacy_insert(self):
        executor = MigrationExecutor(connection)
        ordinary = ("core", "0093_line_registration_session")
        executor.migrate([ordinary])
        legacy_store = executor.loader.project_state([ordinary]).apps.get_model("core", "Store")
        existing = legacy_store.objects.create(name="Ordinary store", slug="ordinary-existing",
                                              line_webhook_token=uuid.uuid4().hex)
        MigrationExecutor(connection).migrate([self.latest])
        self.assertEqual(Store.objects.get(pk=existing.pk).voice_receiver, "groundwire")
        created = legacy_store.objects.create(name="Ordinary after Work", slug="ordinary-new",
                                             line_webhook_token=uuid.uuid4().hex)
        self.assertEqual(Store.objects.get(pk=created.pk).voice_receiver, "groundwire")
