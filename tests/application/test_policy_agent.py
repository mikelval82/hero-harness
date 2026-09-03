from __future__ import annotations

import unittest
from types import SimpleNamespace

from mission_orchestrator.application.policy_agent import PolicyAgentClient
from mission_orchestrator.domain.model_policy import ModelSelection
from mission_orchestrator.domain.phase import PhaseAuthority, PhaseName, PhaseResult
from mission_orchestrator.ports.agent_client import AgentRequest


class _Policy:
    def __init__(self) -> None:
        self.args = None

    def select(self, phase, complexity, retry_count, capabilities):
        self.args = (phase, complexity, retry_count, capabilities)
        return ModelSelection("anthropic", "deep", "deep", "retry escalation", "o5-v1")


class _Agent:
    model = "default"

    def run_phase(self, request):
        return PhaseResult("ok", 1, 0.1, 1, 1)

    def run_conversation(self, request):
        return self.run_phase(request)


class PolicyAgentTest(unittest.TestCase):
    def test_applies_request_routing_and_emits_selection_without_content(self) -> None:
        policy = _Policy()
        events = SimpleNamespace(records=[], publish=lambda kind, payload: events.records.append((kind, payload)))
        agent = _Agent()
        routed = PolicyAgentClient(agent, policy, {"anthropic": {"default": "default", "deep": "deep"}}, events)
        request = AgentRequest("review", "secret system", "secret user", (), [], PhaseAuthority(PhaseName.REVIEW, ()), 1, 30, "L", 2)
        routed.run_phase(request)
        self.assertEqual(policy.args[0:3], ("review", "L", 2))
        self.assertEqual(agent.model, "deep")
        self.assertEqual(events.records[0][1]["requested_model"], "deep")
        self.assertNotIn("secret", str(events.records[0][1]))


if __name__ == "__main__":
    unittest.main()
