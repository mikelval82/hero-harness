import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import src.harness.tasks as tasks_mod
from src.harness.tasks import (
    parse_status_files,
    update_task,
    task_summary,
    is_mission_abort,
    audit_verdict,
    stage_task_files,
)


def _make_harness(tmp_path, tasks=None, status_md=None, audit_md=None):
    h = tmp_path / "harness"
    h.mkdir(exist_ok=True)
    if tasks is not None:
        (h / "tasks.json").write_text(json.dumps(tasks, indent=2), encoding="utf-8")
    if status_md is not None:
        (h / "status.md").write_text(status_md, encoding="utf-8")
    if audit_md is not None:
        (h / "audit.md").write_text(audit_md, encoding="utf-8")
    return h


class TestParseStatusFiles:

    def test_extracts_files(self, tmp_path):
        h = _make_harness(tmp_path, status_md="## Files\n- src/a.py\n- src/b.py\n")
        assert parse_status_files(h) == ["src/a.py", "src/b.py"]

    def test_no_status_file(self, tmp_path):
        h = _make_harness(tmp_path)
        assert parse_status_files(h) == []

    def test_stops_at_next_heading(self, tmp_path):
        h = _make_harness(tmp_path, status_md="## Files\n- a.py\n## Other\n- b.py\n")
        assert parse_status_files(h) == ["a.py"]

    def test_strips_backticks(self, tmp_path):
        h = _make_harness(tmp_path, status_md="## Files\n- `src/x.py`\n")
        assert parse_status_files(h) == ["src/x.py"]


class TestUpdateTask:

    def test_updates_status(self, tmp_path):
        tasks = [{"id": "1", "title": "T1", "status": "pending"}]
        h = _make_harness(tmp_path, tasks=tasks)
        update_task(0, "completed", h)
        result = json.loads((h / "tasks.json").read_text(encoding="utf-8"))
        assert result[0]["status"] == "completed"

    def test_adds_reason(self, tmp_path):
        tasks = [{"id": "1", "title": "T1", "status": "pending"}]
        h = _make_harness(tmp_path, tasks=tasks)
        update_task(0, "failed", h, reason="timeout")
        result = json.loads((h / "tasks.json").read_text(encoding="utf-8"))
        assert result[0]["failure_reason"] == "timeout"

    def test_raises_on_out_of_range(self, tmp_path):
        tasks = [{"id": "1", "title": "T1", "status": "pending"}]
        h = _make_harness(tmp_path, tasks=tasks)
        with pytest.raises(ValueError, match="task index 5 out of range"):
            update_task(5, "completed", h)

    def test_raises_on_negative_index(self, tmp_path):
        tasks = [{"id": "1", "title": "T1", "status": "pending"}]
        h = _make_harness(tmp_path, tasks=tasks)
        with pytest.raises(ValueError, match="task index -1 out of range"):
            update_task(-1, "completed", h)


class TestTaskSummary:

    def test_summary_format(self, tmp_path):
        tasks = [
            {
                "id": "1",
                "status": "completed",
                "complexity": "S",
                "complexity_reason": "single-file low-risk edit",
            },
            {"id": "2", "status": "failed", "failure_reason": "bug"},
            {"id": "3", "status": "pending"},
        ]
        h = _make_harness(tmp_path, tasks=tasks)
        s = task_summary(h)
        assert "Total: 3" in s
        assert "Completed: 1" in s
        assert "Failed: 1" in s
        assert "Pending: 1" in s
        assert "ROUTE [1]: S - single-file low-risk edit" in s
        assert "ROUTE [2]: M - complexity missing; defaulted to M standard route" in s
        assert "FAILED [2]: bug" in s

    def test_no_tasks_json(self, tmp_path):
        h = _make_harness(tmp_path)
        assert "No tasks.json" in task_summary(h)

    def test_listing_includes_complexity_reason(self, tmp_path):
        tasks = [{
            "id": "1",
            "title": "T1",
            "status": "pending",
            "complexity": "L",
            "complexity_reason": "touches many modules and needs bursts",
        }]
        h = _make_harness(tmp_path, tasks=tasks)
        listing = tasks_mod.task_listing(h)
        assert "[PENDING] 1: T1" in listing
        assert "complexity=L" in listing
        assert "touches many modules and needs bursts" in listing


class TestIsMissionAbort:

    def test_user_abort(self):
        assert is_mission_abort("user_abort") is True

    def test_signal(self):
        assert is_mission_abort("signal_SIGINT") is True

    def test_other(self):
        assert is_mission_abort("review[1.1]") is False

    def test_empty(self):
        assert is_mission_abort("") is False


class TestAuditVerdict:

    def test_approved(self, tmp_path):
        h = _make_harness(tmp_path, audit_md="## Verdict\nAPPROVED\n")
        assert audit_verdict(h) == "APPROVED"

    def test_changes_requested(self, tmp_path):
        h = _make_harness(tmp_path, audit_md="## Verdict\nCHANGES_REQUESTED\n")
        assert audit_verdict(h) == "CHANGES_REQUESTED"

    def test_no_file(self, tmp_path):
        h = _make_harness(tmp_path)
        assert audit_verdict(h) == "UNKNOWN"

    def test_no_match(self, tmp_path):
        h = _make_harness(tmp_path, audit_md="nothing relevant\n")
        assert audit_verdict(h) == "UNKNOWN"


class TestStageTaskFiles:

    def test_stages_existing_files(self, tmp_path, monkeypatch):
        h = _make_harness(tmp_path, status_md="## Files\n- src/a.py\n")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "a.py").write_text("a", encoding="utf-8")
        calls = []
        monkeypatch.setattr(tasks_mod, "subprocess", type("M", (), {
            "run": staticmethod(lambda cmd, **kw: calls.append(cmd))
        })())
        monkeypatch.chdir(tmp_path)
        stage_task_files(h)
        assert len(calls) == 1

    def test_no_files_warning(self, tmp_path, monkeypatch):
        h = _make_harness(tmp_path)
        printed = []
        monkeypatch.setattr("builtins.print", lambda *a, **kw: printed.append(str(a)))
        stage_task_files(h)
        assert any("WARNING" in s for s in printed)
