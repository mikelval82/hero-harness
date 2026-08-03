from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping


class PhaseName(Enum):
    RESEARCH = "research"
    STRUCTURE = "structure"
    GRILL = "grill"
    SPEC = "spec"
    PLAN = "plan"
    IMPLEMENT = "implement"
    IMPLEMENT_BURSTS = "implement_bursts"
    REVIEW = "review"
    REIMPLEMENT = "reimplement"
    COMPACT = "compact"
    CONSOLIDATE = "consolidate"
    REPORT = "report"
    REPORT_PLAN = "report_plan"

    @classmethod
    def parse(cls, value: str | "PhaseName") -> "PhaseName":
        if isinstance(value, cls):
            return value
        for phase in cls:
            if phase.value == value:
                return phase
        raise ValueError(f"Unknown phase: {value}")


@dataclass(frozen=True)
class PhaseConfig:
    name: PhaseName
    agent_file: str
    template_file: str
    gate_artifact: str | None
    tools: tuple[str, ...]
    max_turns: int
    timeout_seconds: int
    includes: Mapping[str, str] = field(default_factory=dict)
    is_conversation: bool = False


@dataclass(frozen=True)
class PhaseResult:
    text: str
    turns: int
    elapsed_seconds: float
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class GateResult:
    passed: bool
    detail: str = ""

