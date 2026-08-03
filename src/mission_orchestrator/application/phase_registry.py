from __future__ import annotations

from mission_orchestrator.domain.phase import PhaseConfig, PhaseName

DEFAULT_TOOLS = ("Read", "Write", "Glob", "Grep", "Bash")
IMPL_TOOLS = ("Read", "Write", "Edit", "Glob", "Grep", "Bash")
REVIEW_TOOLS = ("Read", "Write", "Glob", "Grep", "Bash")
DESIGN_TOOLS = (*DEFAULT_TOOLS, "GraphQuery", "GraphPropose")

GRAPH = "__graph_instructions__"

PHASES: dict[PhaseName, PhaseConfig] = {
    PhaseName.RESEARCH: PhaseConfig(
        PhaseName.RESEARCH,
        "researcher.md",
        "brainstorm-prompt.md",
        "brainstorm.md",
        DESIGN_TOOLS,
        75,
        1200,
        {"GRAPH_INSTRUCTIONS": GRAPH},
    ),
    PhaseName.STRUCTURE: PhaseConfig(
        PhaseName.STRUCTURE,
        "structurer.md",
        "structure-prompt.md",
        None,
        DEFAULT_TOOLS,
        30,
        1200,
        {"BRAINSTORM": "brainstorm.md", "BRIEF": "brief.md"},
    ),
    PhaseName.GRILL: PhaseConfig(
        PhaseName.GRILL,
        "griller.md",
        "grill-prompt.md",
        "brief.md",
        DESIGN_TOOLS,
        50,
        3600,
        {"BRAINSTORM": "brainstorm.md", "TASKS": "tasks.json", "GRAPH_INSTRUCTIONS": GRAPH},
        is_conversation=True,
    ),
    PhaseName.SPEC: PhaseConfig(
        PhaseName.SPEC,
        "specifier.md",
        "spec-prompt.md",
        "spec.md",
        DEFAULT_TOOLS,
        30,
        1200,
        {
            "CONTEXT_COLD": "context-cold.md",
            "CONTEXT_HOT": "context-hot.md",
            "BRAINSTORM": "brainstorm.md",
            "TASKS": "tasks.json",
            "BRIEF": "brief.md",
            "GRAPH_INSTRUCTIONS": GRAPH,
        },
    ),
    PhaseName.PLAN: PhaseConfig(
        PhaseName.PLAN,
        "planner.md",
        "plan-prompt.md",
        "plan.md",
        DEFAULT_TOOLS,
        30,
        1200,
        {
            "CONTEXT_COLD": "context-cold.md",
            "CONTEXT_HOT": "context-hot.md",
            "BRAINSTORM": "brainstorm.md",
            "TASKS": "tasks.json",
            "BRIEF": "brief.md",
            "SPEC": "spec.md",
            "GRAPH_INSTRUCTIONS": GRAPH,
        },
    ),
    PhaseName.IMPLEMENT: PhaseConfig(
        PhaseName.IMPLEMENT,
        "implementer.md",
        "implement-prompt.md",
        "status.md",
        IMPL_TOOLS,
        75,
        1200,
        {
            "CONTEXT_COLD": "context-cold.md",
            "CONTEXT_HOT": "context-hot.md",
            "SPEC": "spec.md",
            "PLAN": "plan.md",
            "DECISIONS": "decisions.md",
            "GRAPH_INSTRUCTIONS": GRAPH,
        },
    ),
    PhaseName.IMPLEMENT_BURSTS: PhaseConfig(
        PhaseName.IMPLEMENT_BURSTS,
        "implementer.md",
        "implement-burst-prompt.md",
        "status.md",
        IMPL_TOOLS,
        20,
        300,
        {
            "CONTEXT_COLD": "context-cold.md",
            "CONTEXT_HOT": "context-hot.md",
            "SPEC": "spec.md",
            "DECISIONS": "decisions.md",
            "GRAPH_INSTRUCTIONS": GRAPH,
        },
    ),
    PhaseName.REVIEW: PhaseConfig(
        PhaseName.REVIEW,
        "reviewer.md",
        "review-prompt.md",
        "audit.md",
        REVIEW_TOOLS,
        30,
        1200,
        {"SPEC": "spec.md", "PLAN": "plan.md", "DECISIONS": "decisions.md", "GRAPH_INSTRUCTIONS": GRAPH},
    ),
    PhaseName.REIMPLEMENT: PhaseConfig(
        PhaseName.REIMPLEMENT,
        "implementer.md",
        "reimplement-prompt.md",
        "status.md",
        IMPL_TOOLS,
        75,
        1200,
        {"SPEC": "spec.md", "AUDIT": "audit.md", "STATUS": "status.md", "CONTEXT_HOT": "context-hot.md"},
    ),
    PhaseName.COMPACT: PhaseConfig(
        PhaseName.COMPACT,
        "",
        "compact-prompt.md",
        None,
        ("Read", "Write"),
        10,
        1200,
        {"CONTEXT_HOT": "context-hot.md"},
    ),
    PhaseName.CONSOLIDATE: PhaseConfig(
        PhaseName.CONSOLIDATE,
        "",
        "consolidate-prompt.md",
        None,
        ("Read", "Write"),
        10,
        1200,
        {"TASKS": "tasks.json"},
    ),
    PhaseName.REPORT: PhaseConfig(
        PhaseName.REPORT,
        "",
        "report-full-prompt.md",
        None,
        ("Read", "Write", "Glob"),
        10,
        1200,
        {},
    ),
    PhaseName.REPORT_PLAN: PhaseConfig(
        PhaseName.REPORT_PLAN,
        "",
        "report-plan-only-prompt.md",
        None,
        ("Read", "Write", "Glob"),
        10,
        1200,
        {},
    ),
}


def get_phase_config(name: PhaseName) -> PhaseConfig:
    return PHASES[name]

