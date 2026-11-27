from datetime import date
from types import SimpleNamespace

from django.test import SimpleTestCase

from core.services.settlement_policy import uses_deferred_settlement


class SettlementPolicyTests(SimpleTestCase):
    def test_unconfigured_stores_remain_on_existing_workflow(self):
        store = SimpleNamespace(deferred_settlement_from=None)
        self.assertFalse(uses_deferred_settlement(store, date(2026, 11, 27)))

    def test_cutover_is_inclusive_and_does_not_reclassify_saved_checkouts(self):
        store = SimpleNamespace(deferred_settlement_from=date(2026, 11, 27))
        self.assertFalse(uses_deferred_settlement(store, date(2026, 11, 26)))
        self.assertTrue(uses_deferred_settlement(store, date(2026, 11, 27)))
        saved = SimpleNamespace(cash_handover_recorded=True)
        self.assertFalse(uses_deferred_settlement(store, date(2026, 11, 27), saved))
        saved.cash_handover_recorded = False
        store.deferred_settlement_from = None
        self.assertTrue(uses_deferred_settlement(store, date(2026, 11, 27), saved))
