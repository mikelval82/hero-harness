import json

from src.harness import harness_utils
from src.harness.refiner import (
    REFINER_PROPOSAL_FILE,
    build_refiner_proposal,
    collect_failure_signals,
    extract_failure_signals_from_text,
    write_refiner_proposal,
)
from src.harness.telemetry import write_event


def test_extract_failure_signals_from_failure_taxonomy_text():
    text = """
## Failure Taxonomy
- id: F1
  failure_type: missing_test
  recoverability_lost_at_stage: spec
  evidence: acceptance criterion had no deterministic check
"""

    signals = extract_failure_signals_from_text(text, source="audit.md")

    assert len(signals) == 1
    assert signals[0].failure_type == "missing_test"
    assert signals[0].stage == "spec"
    assert signals[0].signature == "missing_test@spec"


def test_collect_failure_signals_from_artifacts_telemetry_and_case_base(tmp_path):
    harness = tmp_path / "harness"
    harness.mkdir()
    (harness / "audit.md").write_text(
        "failure_type: missing_test\nrecoverability_lost_at_stage: spec\n",
        encoding="utf-8",
    )
    write_event(
        harness,
        "intervention",
        action="retry",
        feedback="retry because semantic_mismatch was found",
    )
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text(
        json.dumps({
            "case_id": "case-1",
            "audit_summary": "failure_type: context_loss\nrecoverability_lost_at_stage: implement\n",
        }) + "\n",
        encoding="utf-8",
    )
    (harness / "_project_cases_path").write_text(str(cases_path), encoding="utf-8")

    signatures = {signal.signature for signal in collect_failure_signals(harness)}

    assert "missing_test@spec" in signatures
    assert "semantic_mismatch@review" in signatures
    assert "context_loss@implement" in signatures


def test_build_refiner_proposal_from_recurrent_failure_signature(tmp_path):
    harness = tmp_path / "harness"
    harness.mkdir()
    (harness / "audit.md").write_text(
        "failure_type: missing_test\nrecoverability_lost_at_stage: spec\n",
        encoding="utf-8",
    )
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text(
        json.dumps({
            "case_id": "case-1",
            "audit_summary": "failure_type: missing_test\nrecoverability_lost_at_stage: spec\n",
        }) + "\n",
        encoding="utf-8",
    )
    (harness / "_project_cases_path").write_text(str(cases_path), encoding="utf-8")

    proposal = build_refiner_proposal(harness)

    assert "approval_required: true" in proposal
    assert "auto_apply: false" in proposal
    assert "missing_test@spec: 2 signals" in proposal
    assert "Strengthen deterministic check coverage" in proposal
    assert "prompts/spec-prompt.md" in proposal
    assert "It does not edit prompts, agents, code, tests, memory, cases, or skills." in proposal


def test_write_refiner_proposal_only_writes_proposal_file(tmp_path):
    harness = tmp_path / "harness"
    harness.mkdir()
    (harness / "audit.md").write_text(
        "failure_type: over_scoping\nrecoverability_lost_at_stage: plan\n",
        encoding="utf-8",
    )
    before = {path.name for path in harness.iterdir()}

    path = write_refiner_proposal(harness, min_recurrence=1)
    after = {path.name for path in harness.iterdir()}

    assert path == harness / REFINER_PROPOSAL_FILE
    assert after - before == {REFINER_PROPOSAL_FILE}
    proposal = path.read_text(encoding="utf-8")
    assert "auto_apply: false" in proposal
    assert "Constrain implementation scope" in proposal


def test_refiner_proposal_no_signals_is_no_change(tmp_path):
    harness = tmp_path / "harness"
    harness.mkdir()

    proposal = build_refiner_proposal(harness)

    assert "failure_signals: 0" in proposal
    assert "## Proposed Harness Changes\n- none" in proposal
    assert "decision: no_change" in proposal


def test_cmd_refiner_proposal_prints_non_application_notice(tmp_path, capsys):
    harness = tmp_path / "harness"
    harness.mkdir()

    harness_utils.cmd_refiner_proposal([str(harness), "1"])

    captured = capsys.readouterr().out
    assert "Refiner proposal written:" in captured
    assert "No prompts, agents, code, tests, memory, cases, or skills were modified." in captured
    assert (harness / REFINER_PROPOSAL_FILE).is_file()
