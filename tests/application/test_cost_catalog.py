from __future__ import annotations

import unittest

from mission_orchestrator.application.cost_catalog import CostLedger, cost_record


class CostCatalogTest(unittest.TestCase):
    def test_uses_served_identity_and_marks_missing_price_unknown(self) -> None:
        catalog = {("anthropic", "served"): (1.0, 2.0)}
        known = cost_record("anthropic", "served", 1_000_000, 500_000, catalog)
        self.assertEqual(known.estimated_usd, 2.0)
        self.assertTrue(known.known)
        unknown = cost_record("anthropic", "requested", 1, 1, catalog)
        self.assertIsNone(unknown.estimated_usd)
        self.assertFalse(unknown.known)

    def test_ledger_preserves_tokens_when_cost_is_unknown_without_double_counting(self) -> None:
        ledger = CostLedger()
        ledger.add(cost_record("p", "known", 3, 4, {("p", "known"): (1.0, 1.0)}))
        ledger.add(cost_record("p", "missing", 5, 6, {}))
        self.assertEqual(ledger.total_tokens, 18)
        self.assertFalse(ledger.known)
        self.assertTrue(ledger.budget_exceeded(17))


if __name__ == "__main__":
    unittest.main()
