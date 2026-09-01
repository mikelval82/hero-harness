from __future__ import annotations

from typing import Protocol

from mission_orchestrator.domain.phase import GateResult


class GateEvaluator(Protocol):
    def evaluate(self, phase_name: str, artifact_name: str) -> GateResult: ...

