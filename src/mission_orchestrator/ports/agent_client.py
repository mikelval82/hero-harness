from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from mission_orchestrator.domain.phase import PhaseAuthority, PhaseResult


@dataclass(frozen=True)
class AgentRequest:
    phase_name: str
    system_prompt: str
    user_prompt: str
    tool_names: tuple[str, ...]
    tool_schemas: list[dict]
    authority: PhaseAuthority
    max_turns: int
    timeout_seconds: int
    complexity: str | None = None
    retry_count: int = 0


@dataclass(frozen=True)
class ConversationRequest(AgentRequest):
    pass


class AgentClient(Protocol):
    def run_phase(self, request: AgentRequest) -> PhaseResult: ...
    def run_conversation(self, request: ConversationRequest) -> PhaseResult: ...
