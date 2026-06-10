from pathlib import Path

import pytest

from src.core.context import (
    MissionContext,
    PhaseConfig,
    PhaseName,
    PHASE_REGISTRY,
    MISSION_PIPELINES,
    PARTIAL_HARNESS_MODES,
    PARTIAL_TASK_PIPELINES,
    TASK_PIPELINES,
    TASK_COMPLEXITY_DESCRIPTIONS,
    DEFAULT_TOOLS,
    IMPL_TOOLS,
    REVIEW_TOOLS,
)


class TestPhaseConfig:

    def test_basic_creation(self):
        pc = PhaseConfig(
            name="test", agent="test.md", template="test-prompt.md",
            gate="output.md", tools=DEFAULT_TOOLS, max_turns=30,
        )
        assert pc.name == "test"
        assert pc.timeout == 1200
        assert pc.includes == {}
        assert pc.is_conversation is False

    def test_with_includes(self):
        pc = PhaseConfig(
            name="spec", agent="specifier.md", template="spec-prompt.md",
            gate="spec.md", tools=DEFAULT_TOOLS, max_turns=30,
            includes={"SPEC": "spec.md"},
        )
        assert pc.includes == {"SPEC": "spec.md"}

    def test_conversation_mode(self):
        pc = PhaseConfig(
            name="grill", agent="griller.md", template="grill-prompt.md",
            gate=None, tools=DEFAULT_TOOLS, max_turns=50,
            is_conversation=True,
        )
        assert pc.is_conversation is True


class TestPhaseRegistry:

    def test_all_required_phases_present(self):
        assert set(PHASE_REGISTRY.keys()) == set(PhaseName)

    def test_research_config(self):
        cfg = PHASE_REGISTRY[PhaseName.RESEARCH]
        assert cfg.agent == "researcher.md"
        assert cfg.template == "brainstorm-prompt.md"
        assert cfg.gate == "brainstorm.md"
        assert cfg.max_turns == 75

    def test_implement_uses_impl_tools(self):
        cfg = PHASE_REGISTRY[PhaseName.IMPLEMENT]
        assert cfg.tools == IMPL_TOOLS
        assert "Edit" in cfg.tools

    def test_review_uses_review_tools(self):
        cfg = PHASE_REGISTRY[PhaseName.REVIEW]
        assert cfg.tools == REVIEW_TOOLS

    def test_grill_is_conversation(self):
        cfg = PHASE_REGISTRY[PhaseName.GRILL]
        assert cfg.is_conversation is True
        assert cfg.timeout == 3600
        assert "BRAINSTORM" in cfg.includes
        assert "TASKS" in cfg.includes
        assert "GRAPH_INSTRUCTIONS" in cfg.includes

    def test_implement_bursts_config(self):
        cfg = PHASE_REGISTRY[PhaseName.IMPLEMENT_BURSTS]
        assert cfg.max_turns == 20
        assert cfg.timeout == 300
        assert "SPEC" in cfg.includes
        assert "DECISIONS" in cfg.includes
        assert "CONTEXT_HOT" in cfg.includes

    def test_reimplement_regrounding_inputs(self):
        cfg = PHASE_REGISTRY[PhaseName.REIMPLEMENT]
        assert "SPEC" in cfg.includes
        assert "AUDIT" in cfg.includes
        assert "STATUS" in cfg.includes
        assert "CONTEXT_HOT" in cfg.includes

    def test_all_configs_have_template(self):
        for name, cfg in PHASE_REGISTRY.items():
            assert cfg.template, f"{name} has no template"

    def test_graph_instructions_phases(self):
        expected = {"research", "grill", "spec", "plan", "implement", "implement_bursts", "review"}
        actual = {n for n, c in PHASE_REGISTRY.items() if "GRAPH_INSTRUCTIONS" in c.includes}
        assert actual == expected

    def test_project_memory_injected_into_agentic_phases(self):
        expected = {
            "research", "structure", "grill", "spec", "plan",
            "implement", "implement_bursts", "review", "reimplement",
        }
        actual = {n for n, c in PHASE_REGISTRY.items() if "PROJECT_MEMORY" in c.includes}
        assert actual == expected
        for phase_name in actual:
            assert PHASE_REGISTRY[phase_name].includes["PROJECT_MEMORY"] == "project-memory.md"

    def test_retrieved_cases_injected_into_agentic_phases(self):
        expected = {
            "research", "structure", "grill", "spec", "plan",
            "implement", "implement_bursts", "review", "reimplement",
        }
        actual = {n for n, c in PHASE_REGISTRY.items() if "MISSION_CASES" in c.includes}
        assert actual == expected
        for phase_name in actual:
            assert PHASE_REGISTRY[phase_name].includes["MISSION_CASES"] == "retrieved-cases.md"

    def test_retrieved_skills_injected_into_agentic_phases(self):
        expected = {
            "research", "structure", "grill", "spec", "plan",
            "implement", "implement_bursts", "review", "reimplement",
        }
        actual = {n for n, c in PHASE_REGISTRY.items() if "RETRIEVED_SKILLS" in c.includes}
        assert actual == expected
        for phase_name in actual:
            assert PHASE_REGISTRY[phase_name].includes["RETRIEVED_SKILLS"] == "retrieved-skills.md"

    def test_gate_phases(self):
        gated = {n for n, c in PHASE_REGISTRY.items() if c.gate}
        assert "research" in gated
        assert "spec" in gated
        assert "plan" in gated
        assert "implement" in gated
        assert "review" in gated
        assert "grill" in gated


class TestMissionPipelines:

    def test_all_modes_present(self):
        expected = {"full", "focused", "spec", "spec-plan", "explore", "hotfix"}
        assert set(MISSION_PIPELINES.keys()) == expected

    def test_full_has_grill(self):
        init = MISSION_PIPELINES["full"]["init"]
        assert "grill?" in init

    def test_grill_before_structure(self):
        for mode in ("full", "spec", "spec-plan"):
            init = MISSION_PIPELINES[mode]["init"]
            if "grill?" in init and "structure" in init:
                assert init.index("grill?") < init.index("structure"), (
                    f"{mode}: grill must run before structure"
                )

    def test_full_has_merge(self):
        assert "merge" in MISSION_PIPELINES["full"]["finalize"]

    def test_spec_plan_no_merge(self):
        assert "merge" not in MISSION_PIPELINES["spec-plan"]["finalize"]

    def test_partial_modes_no_merge(self):
        for mode in PARTIAL_HARNESS_MODES:
            assert "merge" not in MISSION_PIPELINES[mode]["finalize"]

    def test_hotfix_no_init(self):
        assert MISSION_PIPELINES["hotfix"]["init"] == []

    def test_all_pipelines_have_init_and_finalize(self):
        for mode, pipeline in MISSION_PIPELINES.items():
            assert "init" in pipeline, f"{mode} missing init"
            assert "finalize" in pipeline, f"{mode} missing finalize"


class TestTaskPipelines:

    def test_all_complexities_present(self):
        assert set(TASK_PIPELINES.keys()) == {"S", "M", "L"}

    def test_small_is_implement_only(self):
        assert TASK_PIPELINES["S"] == [PhaseName.IMPLEMENT]

    def test_medium_has_review(self):
        assert PhaseName.REVIEW in TASK_PIPELINES["M"]
        assert PhaseName.SPEC in TASK_PIPELINES["M"]

    def test_large_uses_bursts(self):
        assert PhaseName.IMPLEMENT_BURSTS in TASK_PIPELINES["L"]
        assert PhaseName.IMPLEMENT not in TASK_PIPELINES["L"]

    def test_complexities_have_descriptions(self):
        assert set(TASK_COMPLEXITY_DESCRIPTIONS) == set(TASK_PIPELINES)
        assert "implement only" in TASK_COMPLEXITY_DESCRIPTIONS["S"]
        assert "implement_bursts" in TASK_COMPLEXITY_DESCRIPTIONS["L"]

    def test_partial_task_pipelines_present(self):
        assert PARTIAL_TASK_PIPELINES["spec"] == [PhaseName.SPEC]
        assert PARTIAL_TASK_PIPELINES["spec-plan"] == [PhaseName.SPEC, PhaseName.PLAN]


class TestMissionContext:

    def _make_ctx(self, **overrides):
        defaults = dict(
            task="test task", branch="feature/test", mode="full",
            harness=Path("/tmp/harness"), harness_win="/tmp/harness",
            project_dir="/tmp/project", gate="auto", no_grill=False,
            max_tasks=8,
        )
        defaults.update(overrides)
        return MissionContext(**defaults)

    def test_creation(self):
        ctx = self._make_ctx()
        assert ctx.task == "test task"
        assert ctx.notify_prefix == ""

    def test_get_mission_pipeline(self):
        ctx = self._make_ctx(mode="full")
        pipeline = ctx.get_mission_pipeline()
        assert "init" in pipeline
        assert "research" in pipeline["init"]

    def test_get_mission_pipeline_unknown_mode(self):
        ctx = self._make_ctx(mode="unknown")
        pipeline = ctx.get_mission_pipeline()
        assert pipeline == MISSION_PIPELINES["full"]

    def test_get_task_pipeline_medium(self):
        ctx = self._make_ctx()
        pipeline = ctx.get_task_pipeline({"id": "1", "title": "t", "complexity": "M"})
        assert pipeline == [PhaseName.SPEC, PhaseName.PLAN, PhaseName.IMPLEMENT, PhaseName.REVIEW]

    def test_get_task_pipeline_default(self):
        ctx = self._make_ctx()
        pipeline = ctx.get_task_pipeline({"id": "1", "title": "t"})
        assert pipeline == TASK_PIPELINES["M"]

    def test_get_task_pipeline_large(self):
        ctx = self._make_ctx()
        pipeline = ctx.get_task_pipeline({"id": "1", "title": "t", "complexity": "L"})
        assert PhaseName.IMPLEMENT_BURSTS in pipeline

    def test_get_partial_task_pipeline(self):
        ctx = self._make_ctx(mode="spec")
        assert ctx.is_partial_harness_mode() is True
        assert ctx.get_partial_task_pipeline() == [PhaseName.SPEC]

    def test_get_partial_task_pipeline_none_for_full(self):
        ctx = self._make_ctx(mode="full")
        assert ctx.is_partial_harness_mode() is False
        assert ctx.get_partial_task_pipeline() is None

    def test_get_task_complexity_reason_from_task(self):
        ctx = self._make_ctx()
        reason = ctx.get_task_complexity_reason({
            "id": "1",
            "title": "t",
            "complexity": "S",
            "complexity_reason": "single file low risk",
        })
        assert reason == "single file low risk"

    def test_get_task_complexity_reason_default(self):
        ctx = self._make_ctx()
        assert ctx.get_task_complexity({"id": "1", "title": "t"}) == "M"
        assert "defaulted to M" in ctx.get_task_complexity_reason({"id": "1", "title": "t"})

    def test_get_task_pipeline_label(self):
        ctx = self._make_ctx()
        label = ctx.get_task_pipeline_label({"id": "1", "title": "t", "complexity": "S"})
        assert label == "implement"

    def test_get_task_pipeline_label_partial_mode(self):
        ctx = self._make_ctx(mode="spec-plan")
        label = ctx.get_task_pipeline_label({"id": "1", "title": "t", "complexity": "S"})
        assert label == "spec -> plan"

    def test_resume_default_false(self):
        ctx = self._make_ctx()
        assert ctx.resume is False

    def test_resume_set(self):
        ctx = self._make_ctx(resume=True)
        assert ctx.resume is True
