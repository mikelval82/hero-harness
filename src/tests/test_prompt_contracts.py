from pathlib import Path

from src.core.context import PHASE_REGISTRY


AGENT_SIGNATURE_MARKERS = [
    "## Signature",
    "- role:",
    "- inputs:",
    "- outputs:",
    "- responsibilities:",
    "- editable_artifacts (requires_grad):",
    "- read_only_artifacts (no_grad):",
]

PROMPT_SIGNATURE_MARKERS = [
    "## Prompt Signature",
    "- phase:",
    "- inputs:",
    "- outputs:",
    "- responsibilities:",
    "- editable_artifacts (requires_grad):",
]


def test_phase_agents_declare_signature_and_requires_grad_contract():
    agent_names = sorted({config.agent for config in PHASE_REGISTRY.values() if config.agent})
    agent_names.append("content_reviewer.md")

    for agent_name in agent_names:
        text = Path("agents", agent_name).read_text(encoding="utf-8")
        missing = [marker for marker in AGENT_SIGNATURE_MARKERS if marker not in text]
        assert not missing, f"{agent_name} missing signature markers: {missing}"


def test_phase_prompts_declare_inputs_outputs_and_requires_grad_contract():
    prompt_names = sorted({config.template for config in PHASE_REGISTRY.values() if config.template})

    for prompt_name in prompt_names:
        text = Path("prompts", prompt_name).read_text(encoding="utf-8")
        missing = [marker for marker in PROMPT_SIGNATURE_MARKERS if marker not in text]
        assert not missing, f"{prompt_name} missing signature markers: {missing}"


def test_evidence_anchoring_contracts_are_declared():
    reviewer = Path("agents/reviewer.md").read_text(encoding="utf-8")
    implementer = Path("agents/implementer.md").read_text(encoding="utf-8")
    review_prompt = Path("prompts/review-prompt.md").read_text(encoding="utf-8")
    implement_prompt = Path("prompts/implement-prompt.md").read_text(encoding="utf-8")
    audit = Path("research_plan/evidence_anchored_instruction_audit.md").read_text(encoding="utf-8")

    for text in (reviewer, review_prompt):
        assert "Evidence Anchoring" in text
        assert "unsupported_claims" in text
        assert "evidence_quality" in text
        assert "instruction_compliance_risk" in text

    for text in (implementer, implement_prompt):
        assert "NOT_VERIFIED" in text
        assert "Self-Verification" in text

    assert "Instruction-compliance risk" in audit
    assert "unsupported_claim" in audit


def test_complexity_routing_reason_contracts_are_declared():
    structurer = Path("agents/structurer.md").read_text(encoding="utf-8")
    structure_prompt = Path("prompts/structure-prompt.md").read_text(encoding="utf-8")
    implement_prompt = Path("prompts/implement-prompt.md").read_text(encoding="utf-8")
    burst_prompt = Path("prompts/implement-burst-prompt.md").read_text(encoding="utf-8")
    consolidate_prompt = Path("prompts/consolidate-prompt.md").read_text(encoding="utf-8")

    for text in (structurer, structure_prompt, consolidate_prompt):
        assert "complexity_reason" in text

    for text in (implement_prompt, burst_prompt):
        assert "TASK_COMPLEXITY" in text
        assert "TASK_PIPELINE" in text
        assert "TASK_COMPLEXITY_REASON" in text
        assert "## Routing" in text or "Task routing" in text


def test_report_prompts_include_token_cost_summary_contract():
    full_report = Path("prompts/report-full-prompt.md").read_text(encoding="utf-8")
    plan_report = Path("prompts/report-plan-only-prompt.md").read_text(encoding="utf-8")

    for text in (full_report, plan_report):
        assert "TOKEN/COST SUMMARY" in text
        assert "{{TOKEN_COST_SUMMARY}}" in text
        assert "Token/Cost Budget" in text


def test_deterministic_check_registry_contracts_are_declared():
    specifier = Path("agents/specifier.md").read_text(encoding="utf-8")
    reviewer = Path("agents/reviewer.md").read_text(encoding="utf-8")
    implementer = Path("agents/implementer.md").read_text(encoding="utf-8")
    spec_prompt = Path("prompts/spec-prompt.md").read_text(encoding="utf-8")
    review_prompt = Path("prompts/review-prompt.md").read_text(encoding="utf-8")
    implement_prompt = Path("prompts/implement-prompt.md").read_text(encoding="utf-8")
    burst_prompt = Path("prompts/implement-burst-prompt.md").read_text(encoding="utf-8")
    reimplement_prompt = Path("prompts/reimplement-prompt.md").read_text(encoding="utf-8")
    doc = Path("research_plan/deterministic_check_registry.md").read_text(encoding="utf-8")

    for text in (specifier, reviewer, spec_prompt, review_prompt, doc):
        assert "Deterministic Check Registry" in text
        assert "check_registry" in text
        assert "requirement:" in text
        assert "expected:" in text

    for text in (specifier, spec_prompt, doc):
        assert "id: DC1" in text

    for text in (reviewer, review_prompt):
        assert "registry_source:" in text
        assert "checks_executed:" in text
        assert "failed_checks:" in text
        assert "not_run_checks:" in text

    for text in (implementer, implement_prompt, burst_prompt, reimplement_prompt):
        assert "Deterministic Check Registry" in text

    for text in (implementer, implement_prompt, reimplement_prompt):
        assert "deterministic_checks_run" in text


def test_project_memory_contracts_are_declared():
    prompt_names = [
        "brainstorm-prompt.md",
        "structure-prompt.md",
        "grill-prompt.md",
        "spec-prompt.md",
        "plan-prompt.md",
        "implement-prompt.md",
        "implement-burst-prompt.md",
        "review-prompt.md",
        "reimplement-prompt.md",
        "report-full-prompt.md",
        "report-plan-only-prompt.md",
    ]
    for prompt_name in prompt_names:
        text = Path("prompts", prompt_name).read_text(encoding="utf-8")
        assert "PROJECT_MEMORY" in text or "Project memory" in text
        assert "RETRIEVED_SKILLS" in text or "Retrieved verified skills" in text or "RETRIEVED VERIFIED SKILLS" in text
        if not prompt_name.startswith("report-"):
            assert "MISSION_CASES" in text or "Similar approved mission cases" in text

    for agent_name in [
        "researcher.md",
        "structurer.md",
        "griller.md",
        "specifier.md",
        "planner.md",
        "implementer.md",
        "reviewer.md",
    ]:
        text = Path("agents", agent_name).read_text(encoding="utf-8")
        assert "project-memory.md" in text
        assert "retrieved-cases.md" in text
        assert "retrieved-skills.md" in text

    report_full = Path("prompts/report-full-prompt.md").read_text(encoding="utf-8")
    report_plan = Path("prompts/report-plan-only-prompt.md").read_text(encoding="utf-8")
    for text in (report_full, report_plan):
        assert "Do not store secrets" in text
        assert "leave project-memory.md unchanged" in text


def test_mission_case_base_contracts_are_declared():
    doc = Path("research_plan/mission_case_base.md").read_text(encoding="utf-8")
    for marker in ("cases.jsonl", "retrieved-cases.md", "similitud", "aprobadas"):
        assert marker in doc


def test_skill_library_contracts_are_declared():
    doc = Path("research_plan/skill_library.md").read_text(encoding="utf-8")
    for marker in (
        "skills.jsonl",
        "retrieved-skills.md",
        "generated-skills",
        "prompt-gate-contract-change",
        "status: verified",
    ):
        assert marker in doc

    for prompt_name in (
        "brainstorm-prompt.md",
        "structure-prompt.md",
        "grill-prompt.md",
        "spec-prompt.md",
        "plan-prompt.md",
        "implement-prompt.md",
        "implement-burst-prompt.md",
        "review-prompt.md",
        "reimplement-prompt.md",
        "report-full-prompt.md",
        "report-plan-only-prompt.md",
    ):
        text = Path("prompts", prompt_name).read_text(encoding="utf-8")
        assert "RETRIEVED_SKILLS" in text

    for prompt_name in ("report-full-prompt.md", "report-plan-only-prompt.md"):
        text = Path("prompts", prompt_name).read_text(encoding="utf-8")
        assert "generated-skills" in text
        assert "status: verified" in text


def test_refiner_post_mission_contracts_are_declared():
    doc = Path("research_plan/refiner_post_mission.md").read_text(encoding="utf-8")
    prompt = Path("prompts/refiner-prompt.md").read_text(encoding="utf-8")
    agents_map = Path("AGENTS.md").read_text(encoding="utf-8")

    for text in (doc, prompt):
        assert "refiner-proposal.md" in text
        assert "approval_required: true" in text or "aprobacion humana" in text
        assert "auto_apply: false" in text or "No apliques parches" in text
        assert "no" in text.lower()

    for marker in PROMPT_SIGNATURE_MARKERS:
        assert marker in prompt

    assert "/refine-harness" in agents_map
    assert "fallos recurrentes" in doc
    assert "It does not edit prompts, agents, code, tests, memory, cases, or skills." in doc


def test_partial_harness_mode_contracts_are_declared():
    doc = Path("research_plan/partial_harness_mode.md").read_text(encoding="utf-8")
    report_prompt = Path("prompts/report-plan-only-prompt.md").read_text(encoding="utf-8")

    for marker in (
        "--mode spec",
        "--mode spec-plan",
        "--spec-only",
        "--spec-plan",
        "_telemetry.jsonl",
        "stage_task_files",
        "merge_to_develop",
    ):
        assert marker in doc

    assert "spec-only" in report_prompt
    assert "spec+plan" in report_prompt
    assert "report them as N/A" in report_prompt
