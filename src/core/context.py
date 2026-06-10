from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class PhaseName(str, Enum):
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


DEFAULT_TOOLS = "Read,Write,Glob,Grep,Bash"
IMPL_TOOLS = "Read,Write,Edit,Glob,Grep,Bash"
REVIEW_TOOLS = "Read,Write,Glob,Grep,Bash"


@dataclass
class PhaseConfig:
    name: str
    agent: str
    template: str
    gate: Optional[str]
    tools: str
    max_turns: int
    timeout: int = 1200
    includes: dict = field(default_factory=dict)
    variables: dict = field(default_factory=dict)
    is_conversation: bool = False


PHASE_REGISTRY: dict[PhaseName, PhaseConfig] = {
    PhaseName.RESEARCH: PhaseConfig(
        name="research",
        agent="researcher.md",
        template="brainstorm-prompt.md",
        gate="brainstorm.md",
        tools=DEFAULT_TOOLS,
        max_turns=75,
        includes={
            "PROJECT_MEMORY": "project-memory.md",
            "MISSION_CASES": "retrieved-cases.md",
            "RETRIEVED_SKILLS": "retrieved-skills.md",
            "GRAPH_INSTRUCTIONS": "prompts/graph-instructions.md",
        },
    ),
    PhaseName.STRUCTURE: PhaseConfig(
        name="structure",
        agent="structurer.md",
        template="structure-prompt.md",
        gate=None,
        tools=DEFAULT_TOOLS,
        max_turns=30,
        includes={
            "PROJECT_MEMORY": "project-memory.md",
            "MISSION_CASES": "retrieved-cases.md",
            "RETRIEVED_SKILLS": "retrieved-skills.md",
            "BRAINSTORM": "brainstorm.md",
            "BRIEF": "brief.md",
        },
    ),
    PhaseName.GRILL: PhaseConfig(
        name="grill",
        agent="griller.md",
        template="grill-prompt.md",
        gate="brief.md",
        tools=DEFAULT_TOOLS,
        max_turns=50,
        timeout=3600,
        is_conversation=True,
        includes={
            "PROJECT_MEMORY": "project-memory.md",
            "MISSION_CASES": "retrieved-cases.md",
            "RETRIEVED_SKILLS": "retrieved-skills.md",
            "BRAINSTORM": "brainstorm.md",
            "TASKS": "tasks.json",
            "GRAPH_INSTRUCTIONS": "prompts/graph-instructions.md",
        },
    ),
    PhaseName.SPEC: PhaseConfig(
        name="spec",
        agent="specifier.md",
        template="spec-prompt.md",
        gate="spec.md",
        tools=DEFAULT_TOOLS,
        max_turns=30,
        includes={
            "PROJECT_MEMORY": "project-memory.md",
            "MISSION_CASES": "retrieved-cases.md",
            "RETRIEVED_SKILLS": "retrieved-skills.md",
            "CONTEXT_COLD": "context-cold.md",
            "CONTEXT_HOT": "context-hot.md",
            "BRAINSTORM": "brainstorm.md",
            "TASKS": "tasks.json",
            "BRIEF": "brief.md",
            "GRAPH_INSTRUCTIONS": "prompts/graph-instructions.md",
        },
    ),
    PhaseName.PLAN: PhaseConfig(
        name="plan",
        agent="planner.md",
        template="plan-prompt.md",
        gate="plan.md",
        tools=DEFAULT_TOOLS,
        max_turns=30,
        includes={
            "PROJECT_MEMORY": "project-memory.md",
            "MISSION_CASES": "retrieved-cases.md",
            "RETRIEVED_SKILLS": "retrieved-skills.md",
            "CONTEXT_COLD": "context-cold.md",
            "CONTEXT_HOT": "context-hot.md",
            "BRAINSTORM": "brainstorm.md",
            "TASKS": "tasks.json",
            "BRIEF": "brief.md",
            "SPEC": "spec.md",
            "GRAPH_INSTRUCTIONS": "prompts/graph-instructions.md",
        },
    ),
    PhaseName.IMPLEMENT: PhaseConfig(
        name="implement",
        agent="implementer.md",
        template="implement-prompt.md",
        gate="status.md",
        tools=IMPL_TOOLS,
        max_turns=75,
        includes={
            "PROJECT_MEMORY": "project-memory.md",
            "MISSION_CASES": "retrieved-cases.md",
            "RETRIEVED_SKILLS": "retrieved-skills.md",
            "CONTEXT_COLD": "context-cold.md",
            "CONTEXT_HOT": "context-hot.md",
            "SPEC": "spec.md",
            "PLAN": "plan.md",
            "DECISIONS": "decisions.md",
            "GRAPH_INSTRUCTIONS": "prompts/graph-instructions.md",
        },
    ),
    PhaseName.IMPLEMENT_BURSTS: PhaseConfig(
        name="implement_bursts",
        agent="implementer.md",
        template="implement-burst-prompt.md",
        gate="status.md",
        tools=IMPL_TOOLS,
        max_turns=20,
        timeout=300,
        includes={
            "PROJECT_MEMORY": "project-memory.md",
            "MISSION_CASES": "retrieved-cases.md",
            "RETRIEVED_SKILLS": "retrieved-skills.md",
            "CONTEXT_COLD": "context-cold.md",
            "CONTEXT_HOT": "context-hot.md",
            "SPEC": "spec.md",
            "DECISIONS": "decisions.md",
            "GRAPH_INSTRUCTIONS": "prompts/graph-instructions.md",
        },
    ),
    PhaseName.REVIEW: PhaseConfig(
        name="review",
        agent="reviewer.md",
        template="review-prompt.md",
        gate="audit.md",
        tools=REVIEW_TOOLS,
        max_turns=30,
        includes={
            "PROJECT_MEMORY": "project-memory.md",
            "MISSION_CASES": "retrieved-cases.md",
            "RETRIEVED_SKILLS": "retrieved-skills.md",
            "SPEC": "spec.md",
            "PLAN": "plan.md",
            "DECISIONS": "decisions.md",
            "GRAPH_INSTRUCTIONS": "prompts/graph-instructions.md",
        },
    ),
    PhaseName.REIMPLEMENT: PhaseConfig(
        name="reimplement",
        agent="implementer.md",
        template="reimplement-prompt.md",
        gate="status.md",
        tools=IMPL_TOOLS,
        max_turns=75,
        includes={
            "PROJECT_MEMORY": "project-memory.md",
            "MISSION_CASES": "retrieved-cases.md",
            "RETRIEVED_SKILLS": "retrieved-skills.md",
            "SPEC": "spec.md",
            "AUDIT": "audit.md",
            "STATUS": "status.md",
            "CONTEXT_HOT": "context-hot.md",
        },
    ),
    PhaseName.COMPACT: PhaseConfig(
        name="compact",
        agent="",
        template="compact-prompt.md",
        gate=None,
        tools="Read,Write",
        max_turns=10,
    ),
    PhaseName.CONSOLIDATE: PhaseConfig(
        name="consolidate",
        agent="",
        template="consolidate-prompt.md",
        gate=None,
        tools="Read,Write",
        max_turns=10,
    ),
    PhaseName.REPORT: PhaseConfig(
        name="report",
        agent="",
        template="report-full-prompt.md",
        gate=None,
        tools="Read,Write,Glob",
        max_turns=10,
    ),
    PhaseName.REPORT_PLAN: PhaseConfig(
        name="report_plan",
        agent="",
        template="report-plan-only-prompt.md",
        gate=None,
        tools="Read,Write,Glob",
        max_turns=10,
    ),
}


MISSION_PIPELINES: dict[str, dict[str, list[str]]] = {
    "full": {
        "init": ["research", "compact", "grill?", "structure"],
        "finalize": ["report", "merge"],
    },
    "focused": {
        "init": ["research", "structure"],
        "finalize": ["report", "merge"],
    },
    "spec": {
        "init": ["research", "grill?", "structure"],
        "finalize": ["report"],
    },
    "spec-plan": {
        "init": ["research", "grill?", "structure"],
        "finalize": ["report"],
    },
    "explore": {
        "init": ["research"],
        "finalize": ["report"],
    },
    "hotfix": {
        "init": [],
        "finalize": ["report", "merge"],
    },
}


TASK_PIPELINES: dict[str, list[PhaseName]] = {
    "S": [PhaseName.IMPLEMENT],
    "M": [PhaseName.SPEC, PhaseName.PLAN, PhaseName.IMPLEMENT, PhaseName.REVIEW],
    "L": [PhaseName.SPEC, PhaseName.PLAN, PhaseName.IMPLEMENT_BURSTS, PhaseName.REVIEW],
}

PARTIAL_HARNESS_MODES: set[str] = {"spec", "spec-plan"}

PARTIAL_TASK_PIPELINES: dict[str, list[PhaseName]] = {
    "spec": [PhaseName.SPEC],
    "spec-plan": [PhaseName.SPEC, PhaseName.PLAN],
}

TASK_COMPLEXITY_DESCRIPTIONS: dict[str, str] = {
    "S": "simple route: implement only; for small, low-risk, well-scoped edits.",
    "M": "standard route: spec -> plan -> implement -> review; default for normal tasks.",
    "L": "large route: spec -> plan -> implement_bursts -> review; for broad or high-risk tasks.",
}


@dataclass
class MissionContext:
    task: str
    branch: str
    mode: str
    harness: Path
    harness_win: str
    project_dir: str
    gate: str
    no_grill: bool
    max_tasks: int
    resume: bool = False

    notify_prefix: str = ""
    mission_tag: str = ""
    project_name: str = ""

    def get_mission_pipeline(self) -> dict[str, list[str]]:
        return MISSION_PIPELINES.get(self.mode, MISSION_PIPELINES["full"])

    def get_task_pipeline(self, task: dict) -> list[PhaseName]:
        complexity = self.get_task_complexity(task)
        return TASK_PIPELINES.get(complexity, TASK_PIPELINES["M"])

    def get_partial_task_pipeline(self) -> list[PhaseName] | None:
        pipeline = PARTIAL_TASK_PIPELINES.get(self.mode)
        return list(pipeline) if pipeline is not None else None

    def is_partial_harness_mode(self) -> bool:
        return self.mode in PARTIAL_HARNESS_MODES

    def get_task_complexity(self, task: dict) -> str:
        complexity = task.get("complexity", "M")
        return complexity if complexity in TASK_PIPELINES else "M"

    def get_task_complexity_reason(self, task: dict) -> str:
        reason = str(task.get("complexity_reason", "")).strip()
        if reason:
            return reason
        raw_complexity = task.get("complexity")
        if raw_complexity is None:
            return "complexity missing; defaulted to M standard route"
        if raw_complexity not in TASK_PIPELINES:
            return f"unknown complexity {raw_complexity!r}; defaulted to M standard route"
        return f"complexity={raw_complexity} selected without explicit complexity_reason"

    def get_task_pipeline_label(self, task: dict) -> str:
        pipeline = self.get_partial_task_pipeline() or self.get_task_pipeline(task)
        return " -> ".join(phase.value for phase in pipeline)
