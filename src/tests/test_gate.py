import pytest

from src.core.gate import (
    check_gate,
    parse_plan_steps,
    _gate_fail,
    MIN_GATE_LINES,
    GATE_REQUIRED_MARKERS,
)


def _write(tmp_path, name, content):
    f = tmp_path / name
    f.write_text(content, encoding="utf-8")
    return f


SPEC_REGISTRY = (
    "## Deterministic Check Registry (check_registry)\n"
    "- id: DC1\n"
    "  requirement: CA1\n"
    "  type: command\n"
    "  target: src/tests/test_example.py\n"
    "  command: pytest src/tests/test_example.py\n"
    "  expected: tests pass\n"
    "  evidence_hint: pytest output\n"
)


REVIEW_REGISTRY = (
    "### Deterministic Check Registry (check_registry)\n"
    "- registry_source: spec.md#Deterministic Check Registry\n"
    "- checks_executed: DC1\n"
    "- failed_checks: none\n"
    "- not_run_checks: none\n"
    "- DC1:\n"
    "  requirement: CA1\n"
    "  type: command\n"
    "  status: PASS\n"
    "  evidence: pytest src/tests/test_example.py -> passed\n"
)


class TestCheckGate:

    def test_pass_basic(self, tmp_path):
        content = "line1\nline2\nline3\nline4\n**STATUS: DONE**\n"
        passed, reason = check_gate(_write(tmp_path, "out.md", content), "test_phase")
        assert passed is True
        assert reason == ""

    def test_fail_blocked(self, tmp_path):
        content = "line1\nline2\nline3\nline4\n**STATUS: BLOCKED**\n"
        passed, reason = check_gate(_write(tmp_path, "out.md", content), "test_phase")
        assert passed is False
        assert "BLOCKED" in reason

    def test_fail_too_short(self, tmp_path):
        content = "a\nb\nc\n"
        passed, reason = check_gate(_write(tmp_path, "out.md", content), "test_phase")
        assert passed is False
        assert "too short" in reason

    def test_pass_already_done(self, tmp_path):
        content = "line1\nline2\nline3\nline4\n**STATUS: ALREADY_DONE**\n"
        passed, _ = check_gate(_write(tmp_path, "out.md", content), "test_phase")
        assert passed is True

    def test_fail_no_status(self, tmp_path):
        content = "line1\nline2\nline3\nline4\nno status here\n"
        passed, reason = check_gate(_write(tmp_path, "out.md", content), "test_phase")
        assert passed is False
        assert "no STATUS: DONE" in reason

    def test_spec_requires_headers(self, tmp_path):
        content = "line1\nline2\nline3\nline4\n**STATUS: DONE**\n"
        passed, reason = check_gate(_write(tmp_path, "spec.md", content), "spec[1.1]")
        assert passed is False
        assert "missing required section" in reason

    def test_spec_passes_with_headers(self, tmp_path):
        content = (
            "## Objetivo\nblah\n"
            "## Comportamiento Esperado\nblah\n"
            "## Criterios de Aceptacion\n- CA1: works\n"
            f"{SPEC_REGISTRY}"
            "**STATUS: DONE**\n"
        )
        passed, _ = check_gate(_write(tmp_path, "spec.md", content), "spec[1.1]")
        assert passed is True

    def test_spec_requires_check_registry_fields(self, tmp_path):
        content = (
            "## Objetivo\nblah\n"
            "## Comportamiento Esperado\nblah\n"
            "## Deterministic Check Registry (check_registry)\n"
            "- id: DC1\n"
            "  requirement: CA1\n"
            "  type: command\n"
            "**STATUS: DONE**\n"
        )
        passed, reason = check_gate(_write(tmp_path, "spec.md", content), "spec[1.1]")
        assert passed is False
        assert "missing required section" in reason

    def test_implement_requires_self_verification(self, tmp_path):
        content = (
            "## Routing\n"
            "- task_complexity: M\n"
            "- task_pipeline: spec -> plan -> implement -> review\n"
            "- complexity_reason: normal task needs review\n"
            "**STATUS: DONE**\n"
        )
        passed, reason = check_gate(_write(tmp_path, "status.md", content), "implement[1.1]")
        assert passed is False
        assert "missing required section" in reason

    def test_implement_passes_with_self_verification(self, tmp_path):
        content = (
            "## Routing\n"
            "- task_complexity: M\n"
            "- task_pipeline: spec -> plan -> implement -> review\n"
            "- complexity_reason: normal task needs review\n"
            "## Self-Verification\n"
            "- tests_run: pytest - PASS\n"
            "- acceptance_criteria_checked: CA1\n"
            "- edge_cases_considered: empty input\n"
            "- files_touched_reviewed: src/a.py\n"
            "- harness_artifacts_not_written_to_target: yes\n"
            "- known_risks: none\n"
            "**STATUS: DONE**\n"
        )
        passed, _ = check_gate(_write(tmp_path, "status.md", content), "implement[1.1]")
        assert passed is True

    def test_implement_requires_routing_reason(self, tmp_path):
        content = (
            "## Routing\n"
            "- task_complexity: M\n"
            "- task_pipeline: spec -> plan -> implement -> review\n"
            "## Self-Verification\n"
            "- tests_run: pytest - PASS\n"
            "- acceptance_criteria_checked: CA1\n"
            "- edge_cases_considered: empty input\n"
            "- files_touched_reviewed: src/a.py\n"
            "- harness_artifacts_not_written_to_target: yes\n"
            "- known_risks: none\n"
            "**STATUS: DONE**\n"
        )
        passed, reason = check_gate(_write(tmp_path, "status.md", content), "implement[1.1]")
        assert passed is False
        assert "missing required section" in reason

    def test_reimplement_requires_diagnosis(self, tmp_path):
        content = "line1\nline2\nline3\nline4\n**STATUS: DONE**\n"
        passed, reason = check_gate(_write(tmp_path, "status.md", content), "reimplement[1.1]")
        assert passed is False
        assert "missing required section" in reason

    def test_reimplement_requires_self_verification(self, tmp_path):
        content = (
            "## Diagnosis\n"
            "- failed_check: reviewer finding\n"
            "- evidence: audit.md says the parser drops flags\n"
            "- root_cause: previous branch ignored empty args\n"
            "- fix_plan: handle empty args in parse_args only\n"
            "- non_goals: no refactor\n"
            "**STATUS: DONE**\n"
        )
        passed, reason = check_gate(_write(tmp_path, "status.md", content), "reimplement[1.1]")
        assert passed is False
        assert "missing required section" in reason

    def test_reimplement_passes_with_diagnosis_and_self_verification(self, tmp_path):
        content = (
            "## Diagnosis\n"
            "- failed_check: reviewer finding\n"
            "- evidence: audit.md says the parser drops flags\n"
            "- root_cause: previous branch ignored empty args\n"
            "- fix_plan: handle empty args in parse_args only\n"
            "- non_goals: no refactor\n"
            "## Self-Verification\n"
            "- tests_run: pytest - PASS\n"
            "- acceptance_criteria_checked: CA1\n"
            "- edge_cases_considered: empty input\n"
            "- files_touched_reviewed: src/a.py\n"
            "- harness_artifacts_not_written_to_target: yes\n"
            "- known_risks: none\n"
            "**STATUS: DONE**\n"
        )
        passed, _ = check_gate(_write(tmp_path, "status.md", content), "reimplement[1.1]")
        assert passed is True

    def test_review_requires_technical_and_semantic_sections(self, tmp_path):
        content = "## Verdict\nAPPROVED\nline3\nline4\n**STATUS: DONE**\n"
        passed, reason = check_gate(_write(tmp_path, "audit.md", content), "review[1.1]")
        assert passed is False
        assert "missing required section" in reason

    def test_review_requires_evidence_anchoring_section(self, tmp_path):
        content = (
            "## Verdict\n"
            "APPROVED\n"
            "## Technical Review (technical_review)\n"
            "- R1: [x] -> src/a.py:1\n"
            "### Evaluation Hacking Check (evaluation_hacking_check)\n"
            "- hardcoding_outputs: none\n"
            "- special_casing_tests: none\n"
            "- superficial_acceptance: none\n"
            f"{REVIEW_REGISTRY}"
            "### Gradient Findings (textual_gradients)\n"
            "- none\n"
            "## Failure Taxonomy (failure_taxonomy)\n"
            "- failure_type: none\n"
            "  recoverability_lost_at_stage: none\n"
            "## Semantic Audit (semantic_audit)\n"
            "- user_intent_alignment: aligned\n"
            "**STATUS: DONE**\n"
        )
        passed, reason = check_gate(_write(tmp_path, "audit.md", content), "review[1.1]")
        assert passed is False
        assert "missing required section" in reason

    def test_review_requires_evidence_anchoring_fields(self, tmp_path):
        content = (
            "## Verdict\n"
            "APPROVED\n"
            "## Technical Review (technical_review)\n"
            "- R1: [x] -> src/a.py:1\n"
            "### Evidence Anchoring (evidence_anchoring)\n"
            "- none\n"
            "### Evaluation Hacking Check (evaluation_hacking_check)\n"
            "- hardcoding_outputs: none\n"
            "- special_casing_tests: none\n"
            "- superficial_acceptance: none\n"
            "### Gradient Findings (textual_gradients)\n"
            "- none\n"
            "## Failure Taxonomy (failure_taxonomy)\n"
            "- failure_type: none\n"
            "  recoverability_lost_at_stage: none\n"
            "## Semantic Audit (semantic_audit)\n"
            "- user_intent_alignment: aligned\n"
            "**STATUS: DONE**\n"
        )
        passed, reason = check_gate(_write(tmp_path, "audit.md", content), "review[1.1]")
        assert passed is False
        assert "missing required section" in reason

    def test_review_requires_gradient_findings_section(self, tmp_path):
        content = (
            "## Verdict\n"
            "APPROVED\n"
            "## Technical Review (technical_review)\n"
            "- R1: [x] -> src/a.py:1\n"
            "### Evidence Anchoring (evidence_anchoring)\n"
            "- status_claims_checked: yes\n"
            "- unsupported_claims: none\n"
            "- evidence_quality: strong\n"
            "- instruction_compliance_risk: none\n"
            "- evidence: src/a.py:1\n"
            "### Evaluation Hacking Check (evaluation_hacking_check)\n"
            "- hardcoding_outputs: none\n"
            "- special_casing_tests: none\n"
            "- superficial_acceptance: none\n"
            f"{REVIEW_REGISTRY}"
            "## Semantic Audit (semantic_audit)\n"
            "- user_intent_alignment: aligned\n"
            "**STATUS: DONE**\n"
        )
        passed, reason = check_gate(_write(tmp_path, "audit.md", content), "review[1.1]")
        assert passed is False
        assert "missing required section" in reason

    def test_review_requires_evaluation_hacking_check(self, tmp_path):
        content = (
            "## Verdict\n"
            "APPROVED\n"
            "## Technical Review (technical_review)\n"
            "- R1: [x] -> src/a.py:1\n"
            "### Evidence Anchoring (evidence_anchoring)\n"
            "- status_claims_checked: yes\n"
            "- unsupported_claims: none\n"
            "- evidence_quality: strong\n"
            "- instruction_compliance_risk: none\n"
            "- evidence: src/a.py:1\n"
            "### Gradient Findings (textual_gradients)\n"
            "- none\n"
            "## Failure Taxonomy (failure_taxonomy)\n"
            "- failure_type: none\n"
            "  recoverability_lost_at_stage: none\n"
            "## Semantic Audit (semantic_audit)\n"
            "- user_intent_alignment: aligned\n"
            "**STATUS: DONE**\n"
        )
        passed, reason = check_gate(_write(tmp_path, "audit.md", content), "review[1.1]")
        assert passed is False
        assert "missing required section" in reason

    def test_review_requires_evaluation_hacking_fields(self, tmp_path):
        content = (
            "## Verdict\n"
            "APPROVED\n"
            "## Technical Review (technical_review)\n"
            "- R1: [x] -> src/a.py:1\n"
            "### Evidence Anchoring (evidence_anchoring)\n"
            "- status_claims_checked: yes\n"
            "- unsupported_claims: none\n"
            "- evidence_quality: strong\n"
            "- instruction_compliance_risk: none\n"
            "- evidence: src/a.py:1\n"
            "### Evaluation Hacking Check (evaluation_hacking_check)\n"
            "- none\n"
            "### Gradient Findings (textual_gradients)\n"
            "- none\n"
            "## Failure Taxonomy (failure_taxonomy)\n"
            "- failure_type: none\n"
            "  recoverability_lost_at_stage: none\n"
            "## Semantic Audit (semantic_audit)\n"
            "- user_intent_alignment: aligned\n"
            "**STATUS: DONE**\n"
        )
        passed, reason = check_gate(_write(tmp_path, "audit.md", content), "review[1.1]")
        assert passed is False
        assert "missing required section" in reason

    def test_review_requires_failure_taxonomy_section(self, tmp_path):
        content = (
            "## Verdict\n"
            "APPROVED\n"
            "## Technical Review (technical_review)\n"
            "- R1: [x] -> src/a.py:1\n"
            "### Evidence Anchoring (evidence_anchoring)\n"
            "- status_claims_checked: yes\n"
            "- unsupported_claims: none\n"
            "- evidence_quality: strong\n"
            "- instruction_compliance_risk: none\n"
            "- evidence: src/a.py:1\n"
            "### Evaluation Hacking Check (evaluation_hacking_check)\n"
            "- hardcoding_outputs: none\n"
            "- special_casing_tests: none\n"
            "- superficial_acceptance: none\n"
            f"{REVIEW_REGISTRY}"
            "### Gradient Findings (textual_gradients)\n"
            "- none\n"
            "## Semantic Audit (semantic_audit)\n"
            "- user_intent_alignment: aligned\n"
            "**STATUS: DONE**\n"
        )
        passed, reason = check_gate(_write(tmp_path, "audit.md", content), "review[1.1]")
        assert passed is False
        assert "missing required section" in reason

    def test_review_requires_check_registry_fields(self, tmp_path):
        content = (
            "## Verdict\n"
            "APPROVED\n"
            "## Technical Review (technical_review)\n"
            "- R1: [x] -> src/a.py:1\n"
            "### Evidence Anchoring (evidence_anchoring)\n"
            "- status_claims_checked: yes\n"
            "- unsupported_claims: none\n"
            "- evidence_quality: strong\n"
            "- instruction_compliance_risk: none\n"
            "- evidence: src/a.py:1\n"
            "### Evaluation Hacking Check (evaluation_hacking_check)\n"
            "- hardcoding_outputs: none\n"
            "- special_casing_tests: none\n"
            "- superficial_acceptance: none\n"
            "### Deterministic Check Registry (check_registry)\n"
            "- registry_source: spec.md#Deterministic Check Registry\n"
            "- checks_executed: DC1\n"
            "### Gradient Findings (textual_gradients)\n"
            "- none\n"
            "## Failure Taxonomy (failure_taxonomy)\n"
            "- failure_type: none\n"
            "  recoverability_lost_at_stage: none\n"
            "## Semantic Audit (semantic_audit)\n"
            "- user_intent_alignment: aligned\n"
            "**STATUS: DONE**\n"
        )
        passed, reason = check_gate(_write(tmp_path, "audit.md", content), "review[1.1]")
        assert passed is False
        assert "missing required section" in reason

    def test_review_requires_failure_taxonomy_fields(self, tmp_path):
        content = (
            "## Verdict\n"
            "APPROVED\n"
            "## Technical Review (technical_review)\n"
            "- R1: [x] -> src/a.py:1\n"
            "### Evidence Anchoring (evidence_anchoring)\n"
            "- status_claims_checked: yes\n"
            "- unsupported_claims: none\n"
            "- evidence_quality: strong\n"
            "- instruction_compliance_risk: none\n"
            "- evidence: src/a.py:1\n"
            "### Evaluation Hacking Check (evaluation_hacking_check)\n"
            "- hardcoding_outputs: none\n"
            "- special_casing_tests: none\n"
            "- superficial_acceptance: none\n"
            "### Gradient Findings (textual_gradients)\n"
            "- none\n"
            "## Failure Taxonomy (failure_taxonomy)\n"
            "- none\n"
            "## Semantic Audit (semantic_audit)\n"
            "- user_intent_alignment: aligned\n"
            "**STATUS: DONE**\n"
        )
        passed, reason = check_gate(_write(tmp_path, "audit.md", content), "review[1.1]")
        assert passed is False
        assert "missing required section" in reason

    def test_review_passes_with_taxonomy_and_required_sections(self, tmp_path):
        content = (
            "## Verdict\n"
            "APPROVED\n"
            "## Technical Review (technical_review)\n"
            "- R1: [x] -> src/a.py:1\n"
            "### Evidence Anchoring (evidence_anchoring)\n"
            "- status_claims_checked: yes\n"
            "- unsupported_claims: none\n"
            "- evidence_quality: strong\n"
            "- instruction_compliance_risk: none\n"
            "- evidence: src/a.py:1\n"
            "### Evaluation Hacking Check (evaluation_hacking_check)\n"
            "- hardcoding_outputs: none\n"
            "- special_casing_tests: none\n"
            "- superficial_acceptance: none\n"
            "- hidden_shortcuts: none\n"
            "- evidence: none\n"
            "- risk: none\n"
            f"{REVIEW_REGISTRY}"
            "### Gradient Findings (textual_gradients)\n"
            "- none\n"
            "## Failure Taxonomy (failure_taxonomy)\n"
            "- failure_type: none\n"
            "  recoverability_lost_at_stage: none\n"
            "## Semantic Audit (semantic_audit)\n"
            "- user_intent_alignment: aligned\n"
            "**STATUS: DONE**\n"
        )
        passed, _ = check_gate(_write(tmp_path, "audit.md", content), "review[1.1]")
        assert passed is True

    def test_log_callback_called(self, tmp_path):
        content = "line1\nline2\nline3\nline4\n**STATUS: DONE**\n"
        logs = []
        check_gate(_write(tmp_path, "out.md", content), "test_phase", log=logs.append)
        assert any("GATE PASS" in m for m in logs)


class TestParsePlanSteps:

    def test_multiple_steps(self):
        plan = "## Changes\n### 1. First\ndo A\n### 2. Second\ndo B\n"
        steps = parse_plan_steps(plan)
        assert len(steps) == 2
        assert "First" in steps[0]
        assert "Second" in steps[1]

    def test_no_section(self):
        assert parse_plan_steps("## Unrelated\nstuff\n") == []

    def test_no_numbered_steps(self):
        assert parse_plan_steps("## Changes\nno steps here\n") == []

    def test_alternative_heading(self):
        plan = "## Pasos\n### 1. Uno\nhacer A\n"
        steps = parse_plan_steps(plan)
        assert len(steps) == 1


class TestGateFail:

    def test_returns_false_and_reason(self):
        passed, reason = _gate_fail("phase", "some reason")
        assert passed is False
        assert reason == "some reason"

    def test_calls_log(self):
        logs = []
        _gate_fail("phase", "bad", log=logs.append)
        assert len(logs) == 1
        assert "GATE FAIL" in logs[0]


class TestConstants:

    def test_min_gate_lines(self):
        assert MIN_GATE_LINES == 4

    def test_required_markers_keys(self):
        assert set(GATE_REQUIRED_MARKERS.keys()) == {
            "grill",
            "spec",
            "plan",
            "implement",
            "review",
            "reimplement",
        }
