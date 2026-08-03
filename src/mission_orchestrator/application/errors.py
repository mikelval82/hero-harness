from __future__ import annotations

from mission_orchestrator.domain.phase import PhaseResult


class AgentLoopError(Exception):
    def __init__(self, message: str, metrics: PhaseResult | None = None) -> None:
        super().__init__(message)
        self.metrics = metrics


class PhaseTimeout(AgentLoopError):
    pass


class MaxTurnsExceeded(AgentLoopError):
    pass


class MaxRetriesExceeded(AgentLoopError):
    pass

