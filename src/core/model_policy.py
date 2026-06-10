from __future__ import annotations

import os
from dataclasses import dataclass


CHEAP_MODEL = "claude-haiku-4-5"
DEFAULT_MODEL = "claude-sonnet-4-6"
DEEP_MODEL = "claude-opus-4-7"

MODEL_FORCE_ENV = "CLAUDE_HARNESS_MODEL_FORCE"
MODEL_CHEAP_ENV = "CLAUDE_HARNESS_MODEL_CHEAP"
MODEL_DEFAULT_ENV = "CLAUDE_HARNESS_MODEL_DEFAULT"
MODEL_DEEP_ENV = "CLAUDE_HARNESS_MODEL_DEEP"

MODEL_TIERS = {
    "cheap": CHEAP_MODEL,
    "default": DEFAULT_MODEL,
    "deep": DEEP_MODEL,
}

MODEL_ENV_BY_TIER = {
    "cheap": MODEL_CHEAP_ENV,
    "default": MODEL_DEFAULT_ENV,
    "deep": MODEL_DEEP_ENV,
}

CHEAP_PHASES = {"compact", "consolidate", "report", "report_plan"}
DEEP_PHASES = {"grill", "review", "reimplement"}
TASK_PHASES = {"spec", "plan", "implement", "implement_bursts", "review", "reimplement"}

MODEL_PRICING_USD_PER_MTOK = {
    "claude-opus-4-7": {"input": 5.0, "output": 25.0},
    "claude-opus-4-6": {"input": 5.0, "output": 25.0},
    "claude-opus-4-5": {"input": 5.0, "output": 25.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-sonnet-4-5": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0},
}


@dataclass(frozen=True)
class ModelSelection:
    tier: str
    model: str
    reason: str


def _env(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def normalize_phase_name(phase_name: str) -> str:
    phase = str(phase_name or "").strip()
    if "[" in phase:
        phase = phase.split("[", 1)[0]
    if "#" in phase:
        phase = phase.split("#", 1)[0]
    return phase


def resolve_model_id(tier: str) -> str:
    forced = _env(MODEL_FORCE_ENV)
    if forced:
        return forced
    tier = tier if tier in MODEL_TIERS else "default"
    override = _env(MODEL_ENV_BY_TIER[tier])
    return override or MODEL_TIERS[tier]


def select_model_for_phase(
    phase_name: str,
    *,
    mode: str = "full",
    task_complexity: str | None = None,
    retry_count: int = 0,
) -> ModelSelection:
    phase = normalize_phase_name(phase_name)
    complexity = (task_complexity or "").strip().upper()

    if _env(MODEL_FORCE_ENV):
        return ModelSelection("forced", resolve_model_id("default"), f"forced via {MODEL_FORCE_ENV}")

    if retry_count > 0:
        return ModelSelection("deep", resolve_model_id("deep"), "retry escalation")
    if phase in CHEAP_PHASES:
        return ModelSelection("cheap", resolve_model_id("cheap"), f"{phase} is low-risk summarization/reporting")
    if phase in DEEP_PHASES:
        return ModelSelection("deep", resolve_model_id("deep"), f"{phase} requires high-confidence reasoning")
    if complexity == "L" and phase in TASK_PHASES:
        return ModelSelection("deep", resolve_model_id("deep"), "large task complexity")
    if mode == "explore" and phase == "research":
        return ModelSelection("deep", resolve_model_id("deep"), "explore mode research")
    return ModelSelection("default", resolve_model_id("default"), "standard harness phase")


def estimate_cost_usd(model: str | None, input_tokens: int = 0, output_tokens: int = 0) -> float | None:
    if not model:
        return None
    pricing = MODEL_PRICING_USD_PER_MTOK.get(model)
    if pricing is None:
        return None
    input_cost = (int(input_tokens or 0) / 1_000_000) * pricing["input"]
    output_cost = (int(output_tokens or 0) / 1_000_000) * pricing["output"]
    return round(input_cost + output_cost, 6)
