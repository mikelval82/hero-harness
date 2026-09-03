from __future__ import annotations

import unittest

from mission_orchestrator.application.model_policy import DeterministicModelPolicy


CAPABILITIES = {"anthropic": {"cheap": "cheap", "default": "default", "deep": "deep"}}


class DeterministicModelPolicyTest(unittest.TestCase):
    def test_phase_complexity_and_retry_select_deterministically(self) -> None:
        policy = DeterministicModelPolicy("anthropic")
        self.assertEqual(policy.select("report", None, 0, CAPABILITIES).tier, "cheap")
        self.assertEqual(policy.select("research", None, 0, CAPABILITIES).tier, "cheap")
        self.assertEqual(policy.select("spec", None, 0, CAPABILITIES).tier, "deep")
        self.assertEqual(policy.select("plan", None, 0, CAPABILITIES).tier, "deep")
        self.assertEqual(policy.select("implement", "L", 0, CAPABILITIES).reason, "large task complexity")
        self.assertEqual(policy.select("implement", "M", 0, CAPABILITIES).tier, "default")
        self.assertEqual(policy.select("report", None, 1, CAPABILITIES).requested_model, "deep")

    def test_forced_model_must_be_declared(self) -> None:
        policy = DeterministicModelPolicy("anthropic", forced_model="missing")
        with self.assertRaisesRegex(ValueError, "not declared"):
            policy.select("spec", None, 0, CAPABILITIES)

    def test_forced_model_is_reproducible(self) -> None:
        policy = DeterministicModelPolicy("anthropic", forced_model="default")
        selection = policy.select("review", "L", 2, CAPABILITIES)
        self.assertEqual((selection.tier, selection.reason, selection.policy_version), ("forced", "explicit runtime override", "o5-v1"))

    def test_unknown_provider_fails_closed_without_fallback(self) -> None:
        with self.assertRaisesRegex(ValueError, "no capabilities"):
            DeterministicModelPolicy("deepseek").select("spec", None, 0, CAPABILITIES)


if __name__ == "__main__":
    unittest.main()
