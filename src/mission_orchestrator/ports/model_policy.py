from __future__ import annotations

from typing import Mapping, Protocol

from mission_orchestrator.domain.model_policy import ModelSelection


class ModelPolicyPort(Protocol):
    def select(
        self,
        phase: str,
        complexity: str | None,
        retry_count: int,
        provider_capabilities: Mapping[str, Mapping[str, str]],
    ) -> ModelSelection: ...
