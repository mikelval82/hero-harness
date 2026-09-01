from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from mission_orchestrator.domain.model_policy import ModelSelection
from mission_orchestrator.domain.phase import PhaseResult
from mission_orchestrator.ports.agent_client import AgentClient, AgentRequest, ConversationRequest
from mission_orchestrator.ports.events import EventPublisher
from mission_orchestrator.ports.model_policy import ModelPolicyPort


@dataclass
class PolicyAgentClient:
    """Applies runtime-owned model selection before delegating to one adapter."""

    agent: AgentClient
    policy: ModelPolicyPort
    capabilities: Mapping[str, Mapping[str, str]]
    events: EventPublisher

    def run_phase(self, request: AgentRequest) -> PhaseResult:
        return self._run(request, False)

    def run_conversation(self, request: ConversationRequest) -> PhaseResult:
        return self._run(request, True)

    def _run(self, request: AgentRequest, conversation: bool) -> PhaseResult:
        selection = self.policy.select(
            request.phase_name, request.complexity, request.retry_count, self.capabilities
        )
        self._apply(selection)
        self.events.publish("model_selection", {
            "phase": request.phase_name, "requested_provider": selection.requested_provider,
            "requested_model": selection.requested_model, "tier": selection.tier,
            "reason": selection.reason, "policy_version": selection.policy_version,
        })
        return self.agent.run_conversation(request) if conversation else self.agent.run_phase(request)

    def _apply(self, selection: ModelSelection) -> None:
        if not hasattr(self.agent, "model"):
            raise ValueError("selected agent does not expose a model")
        setattr(self.agent, "model", selection.requested_model)
