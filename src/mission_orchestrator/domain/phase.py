from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import PurePosixPath
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
class PhaseAuthority:
    """The effective tool and write authority for one runtime phase.

    Tool schemas are only a projection of this object. The tool registry receives
    the same authority again when dispatching a provider tool call.
    """

    phase: PhaseName
    tools: tuple[str, ...]
    allow_project_writes: bool = False
    harness_write_paths: tuple[str, ...] = ()
    harness_mutation_tools: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if len(set(self.tools)) != len(self.tools):
            raise ValueError(f"duplicate tools declared for {self.phase.value}")
        if not set(self.harness_mutation_tools).issubset(self.tools):
            raise ValueError(f"undeclared harness mutation tool for {self.phase.value}")
        for raw_path in self.harness_write_paths:
            path = PurePosixPath(raw_path)
            if not raw_path or path.is_absolute() or ".." in path.parts or str(path) == ".":
                raise ValueError(f"invalid harness artifact path for {self.phase.value}: {raw_path}")

    def to_payload(self) -> dict[str, object]:
        return {
            "phase": self.phase.value,
            "tools": list(self.tools),
            "allow_project_writes": self.allow_project_writes,
            "harness_write_paths": list(self.harness_write_paths),
            "harness_mutation_tools": list(self.harness_mutation_tools),
        }


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
    allow_project_writes: bool = False
    harness_write_paths: tuple[str, ...] = ()
    harness_mutation_tools: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.gate_artifact and self.gate_artifact not in self.harness_write_paths:
            raise ValueError(
                f"gate artifact {self.gate_artifact} is not writable in phase {self.name.value}"
            )

    @property
    def authority(self) -> PhaseAuthority:
        return PhaseAuthority(
            phase=self.name,
            tools=self.tools,
            allow_project_writes=self.allow_project_writes,
            harness_write_paths=self.harness_write_paths,
            harness_mutation_tools=self.harness_mutation_tools,
        )


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
