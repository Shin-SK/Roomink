"""Helpers for historical-schema tests in Django's disposable test database."""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


def migrate_test_schema(targets):
    executor = MigrationExecutor(connection)
    plan = executor.migration_plan(targets)
    if plan and all(backwards for _, backwards in plan):
        # Independent branches may both alter the same SQLite table. Django's
        # per-child reverse traversal can differ from its forward state order,
        # so a table rebuild can lose a sibling field before RemoveField runs.
        # Reverse the actual forward order while preserving the same plan set.
        full_plan = executor.migration_plan(executor.loader.graph.leaf_nodes(), clean_start=True)
        reversing = {migration for migration, _ in plan}
        plan = [(migration, True) for migration, _ in reversed(full_plan)
                if migration in reversing]
    return executor.migrate(targets, plan=plan)
