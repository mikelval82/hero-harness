from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from mission_orchestrator.domain.model_policy import ModelSelection


CHEAP_PHASES = frozenset({"compact", "consolidate", "report", "report_plan"})
DEEP_PHASES = frozenset({"grill", "review", "reimplement"})
POLICY_VERSION = "o4-v1"


@dataclass(frozen=True)
class DeterministicModelPolicy:
    default_provider: str
    forced_provider: str | None = None
    forced_model: str | None = None

    def select(
        self,
        phase: str,
        complexity: str | None,
        retry_count: int,
        provider_capabilities: Mapping[str, Mapping[str, str]],
    ) -> ModelSelection:
        provider = self.forced_provider or self.default_provider
        capabilities = provider_capabilities.get(provider)
        if not capabilities:
            raise ValueError(f"model policy has no capabilities for provider: {provider}")
        if self.forced_model:
            if self.forced_model not in set(capabilities.values()):
                raise ValueError(f"forced model is not declared for provider {provider}: {self.forced_model}")
            return ModelSelection(provider, self.forced_model, "forced", "explicit runtime override", POLICY_VERSION)
        tier, reason = self._tier(phase, complexity, retry_count)
        model = capabilities.get(tier) or capabilities.get("default")
        if not model:
            raise ValueError(f"provider {provider} has no {tier} or default model")
        return ModelSelection(provider, model, tier, reason, POLICY_VERSION)

    @staticmethod
    def _tier(phase: str, complexity: str | None, retry_count: int) -> tuple[str, str]:
        if retry_count > 0:
            return "deep", "retry escalation"
        if phase in CHEAP_PHASES:
            return "cheap", f"{phase} is low-risk summarization/reporting"
        if phase in DEEP_PHASES:
            return "deep", f"{phase} requires high-confidence reasoning"
        if (complexity or "").upper() == "L":
            return "deep", "large task complexity"
        return "default", "standard harness phase"
