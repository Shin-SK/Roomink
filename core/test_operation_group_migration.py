from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class OperationGroupMigrationTest(TransactionTestCase):
    migrate_from = [("core", "0081_store_memberships_and_invitations")]
    migrate_to = [("core", "0082_operation_groups")]

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps

        User = old_apps.get_model("auth", "User")
        Store = old_apps.get_model("core", "Store")
        StoreMembership = old_apps.get_model("core", "StoreMembership")
        self.manager = User.objects.create(username="legacy-group-manager")
        self.inactive_manager = User.objects.create(username="legacy-inactive-manager")
        self.store = Store.objects.create(name="既存契約店", slug="legacy-contract-store")
        StoreMembership.objects.create(
            user=self.manager,
            store=self.store,
            role="manager",
            is_active=True,
        )
        StoreMembership.objects.create(
            user=self.inactive_manager,
            store=self.store,
            role="manager",
            is_active=False,
        )

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        self.apps = executor.loader.project_state(self.migrate_to).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_existing_store_becomes_private_single_store_group(self):
        Store = self.apps.get_model("core", "Store")
        OperationGroup = self.apps.get_model("core", "OperationGroup")
        OperationGroupMembership = self.apps.get_model("core", "OperationGroupMembership")
        OperationGroupEvent = self.apps.get_model("core", "OperationGroupEvent")

        store = Store.objects.get(pk=self.store.pk)
        self.assertIsNotNone(store.operation_group_id)
        self.assertEqual(
            OperationGroup.objects.filter(stores__pk=store.pk).count(),
            1,
        )
        self.assertEqual(
            OperationGroup.objects.get(pk=store.operation_group_id).internal_label,
            f"契約グループ {store.pk}",
        )
        self.assertTrue(
            OperationGroupMembership.objects.filter(
                operation_group_id=store.operation_group_id,
                user_id=self.manager.pk,
                role="manager",
                is_active=True,
            ).exists()
        )
        self.assertFalse(
            OperationGroupMembership.objects.filter(
                operation_group_id=store.operation_group_id,
                user_id=self.inactive_manager.pk,
            ).exists()
        )
        self.assertEqual(
            set(
                OperationGroupEvent.objects.filter(
                    operation_group_id=store.operation_group_id,
                ).values_list("action", flat=True)
            ),
            {"legacy_group_created", "legacy_manager_granted"},
        )
