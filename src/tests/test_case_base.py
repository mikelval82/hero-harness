import json

from src.core.block_state import BlockKind, BlockReason, BlockState
from src.harness.case_base import (
    CASES_FILE,
    HARNESS_CASES_FILE,
    HARNESS_CASES_PATH_FILE,
    append_case,
    build_mission_case,
    case_base_path,
    ensure_case_base,
    format_retrieved_cases,
    read_cases,
    retrieve_cases,
    save_approved_mission_case,
    stage_retrieved_cases,
)


def _make_approved_harness(tmp_path):
    harness = tmp_path / "harness"
    harness.mkdir()
    (harness / "tasks.json").write_text(
        json.dumps([{"id": "1", "title": "Routing task", "status": "completed"}]),
        encoding="utf-8",
    )
    (harness / "brief.md").write_text("Need complexity routing.", encoding="utf-8")
    (harness / "spec.md").write_text("R1 complexity routing shall be logged.", encoding="utf-8")
    (harness / "plan.md").write_text("Update routing code and tests.", encoding="utf-8")
    (harness / "decisions.md").write_text("Decision: use existing route helpers.", encoding="utf-8")
    (harness / "status.md").write_text(
        "## Files\n"
        "- src/core/context.py\n"
        "## Validation\n"
        "- pytest src/tests/test_context.py -> PASS\n",
        encoding="utf-8",
    )
    (harness / "audit.md").write_text("## Verdict\nAPPROVED\n", encoding="utf-8")
    (harness / "mission-report.md").write_text("Routing mission approved.", encoding="utf-8")
    return harness


def test_ensure_case_base_creates_jsonl(tmp_path):
    project = tmp_path / "repo"
    project.mkdir()

    path = ensure_case_base(project, base_dir=tmp_path / "memory")

    assert path.name == CASES_FILE
    assert path.is_file()
    assert path.read_text(encoding="utf-8") == ""


def test_append_case_deduplicates_by_case_id(tmp_path):
    path = tmp_path / "cases.jsonl"
    case = {"case_id": "C1", "task": "first"}

    assert append_case(path, case) is True
    assert append_case(path, case) is False

    assert len(read_cases(path)) == 1


def test_retrieve_cases_returns_most_similar(tmp_path):
    path = tmp_path / "cases.jsonl"
    append_case(path, {"case_id": "C1", "task": "routing", "retrieval_text": "complexity routing gate"})
    append_case(path, {"case_id": "C2", "task": "docs", "retrieval_text": "documentation copy update"})

    results = retrieve_cases(path, "fix complexity routing reason", top_k=1)

    assert [c["case_id"] for c in results] == ["C1"]
    assert results[0]["similarity_score"] > 0


def test_format_retrieved_cases_empty():
    text = format_retrieved_cases([])

    assert "No similar approved mission cases" in text


def test_stage_retrieved_cases_writes_markdown_and_pointer(tmp_path):
    project = tmp_path / "repo"
    harness = tmp_path / "harness"
    project.mkdir()
    harness.mkdir()
    path = ensure_case_base(project, base_dir=tmp_path / "memory")
    append_case(path, {
        "case_id": "C1",
        "task": "complexity routing",
        "outcome": "APPROVED",
        "retrieval_text": "complexity routing",
    })

    info = stage_retrieved_cases(project, harness, query="routing", base_dir=tmp_path / "memory")

    assert info["persistent"] == case_base_path(project, base_dir=tmp_path / "memory")
    assert (harness / HARNESS_CASES_FILE).is_file()
    assert (harness / HARNESS_CASES_PATH_FILE).read_text(encoding="utf-8") == str(path)
    assert "Case 1" in (harness / HARNESS_CASES_FILE).read_text(encoding="utf-8")


def test_build_mission_case_extracts_artifacts(tmp_path):
    project = tmp_path / "repo"
    project.mkdir()
    harness = _make_approved_harness(tmp_path)

    case = build_mission_case(
        harness,
        task="Add complexity routing",
        branch="feature/routing",
        mode="full",
        project_dir=project,
    )

    assert case["outcome"] == "APPROVED"
    assert case["task"] == "Add complexity routing"
    assert case["files_changed"] == ["src/core/context.py"]
    assert case["audit_verdict"] == "APPROVED"
    assert "complexity routing" in case["retrieval_text"].lower()


def test_save_approved_mission_case_appends_to_case_base(tmp_path):
    project = tmp_path / "repo"
    project.mkdir()
    harness = _make_approved_harness(tmp_path)
    cases_path = tmp_path / "memory" / "cases.jsonl"
    (harness / HARNESS_CASES_PATH_FILE).write_text(str(cases_path), encoding="utf-8")

    saved = save_approved_mission_case(
        harness,
        task="Add complexity routing",
        branch="feature/routing",
        mode="full",
        project_dir=project,
        blocked=BlockState(),
    )

    assert saved is True
    cases = read_cases(cases_path)
    assert len(cases) == 1
    assert cases[0]["task"] == "Add complexity routing"


def test_save_approved_mission_case_skips_blocked_or_failed(tmp_path):
    project = tmp_path / "repo"
    project.mkdir()
    harness = _make_approved_harness(tmp_path)
    cases_path = tmp_path / "memory" / "cases.jsonl"
    (harness / HARNESS_CASES_PATH_FILE).write_text(str(cases_path), encoding="utf-8")

    blocked = BlockState()
    blocked.reason = BlockReason(BlockKind.TIMEOUT, phase="review")
    assert save_approved_mission_case(
        harness,
        task="Add complexity routing",
        branch="feature/routing",
        mode="full",
        project_dir=project,
        blocked=blocked,
    ) is False

    tasks = [{"id": "1", "title": "Routing task", "status": "failed"}]
    (harness / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")
    assert save_approved_mission_case(
        harness,
        task="Add complexity routing",
        branch="feature/routing",
        mode="full",
        project_dir=project,
        blocked=BlockState(),
    ) is False
    assert not cases_path.exists()
