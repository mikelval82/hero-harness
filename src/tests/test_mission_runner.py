import json
import queue
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.block_state import BlockState, BlockKind, BlockReason
from src.core.context import MissionContext, PHASE_REGISTRY
from src.mission.runner import MissionRunner, create_runner
from src.mission.burst_runner import BurstRunner
from src.mission.hitl import HitlReviewer
from src.mission.phase_runner import PhaseRunner
from src.agent.loop import PhaseResult, PhaseTimeout, MaxTurnsExceeded, MaxRetriesExceeded
from src.harness.case_base import HARNESS_CASES_PATH_FILE, read_cases
from src.harness.skill_library import HARNESS_GENERATED_SKILLS_DIR, HARNESS_SKILLS_PATH_FILE, read_skill_index
from src.harness.telemetry import read_events
from src.integrations.telegram_listener import MissionState
import src.mission.runner as runner_mod
import src.mission.burst_runner as burst_mod
import src.mission.hitl as hitl_mod


def _make_ctx(tmp_path, **overrides):
    harness = tmp_path / "harness"
    harness.mkdir(exist_ok=True)
    (harness / "_gate_mode").write_text("auto", encoding="utf-8")
    defaults = dict(
        task="test task", branch="feature/test", mode="full",
        harness=harness, harness_win=str(harness),
        project_dir=str(tmp_path), gate="auto", no_grill=False,
        max_tasks=8,
    )
    defaults.update(overrides)
    return MissionContext(**defaults)


def _make_runner(tmp_path, monkeypatch, ctx=None, blocked=None):
    if ctx is None:
        ctx = _make_ctx(tmp_path)
    if blocked is None:
        blocked = BlockState()
    monkeypatch.setattr(runner_mod, "notify", lambda msg: None)
    monkeypatch.setattr(runner_mod, "update_state", lambda *a, **kw: None)
    monkeypatch.setattr(runner_mod, "check_signals", lambda *a, **kw: True)
    monkeypatch.setattr(runner_mod, "build_code_graph", lambda *a, **kw: None)
    monkeypatch.setattr(runner_mod, "generate_report", lambda *a, **kw: None)
    monkeypatch.setattr(runner_mod, "notify_result", lambda *a, **kw: None)
    monkeypatch.setattr(runner_mod, "final_commit", lambda t, s: None)
    monkeypatch.setattr(runner_mod, "merge_to_develop", lambda b, l: True)
    monkeypatch.setattr(hitl_mod, "notify", lambda msg: None)
    monkeypatch.setattr(hitl_mod, "update_state", lambda *a, **kw: None)
    monkeypatch.setattr("builtins.print", lambda *a, **kw: None)
    ms = MissionState()
    cq = queue.Queue()
    runner = create_runner(MagicMock(), ctx, cq, ms, lambda m: None, blocked)
    return runner


def test_generate_report_syncs_project_memory(tmp_path, monkeypatch):
    ctx = _make_ctx(tmp_path)
    persistent = tmp_path / "persistent-memory.md"
    (ctx.harness / "_project_memory_path").write_text(str(persistent), encoding="utf-8")
    (ctx.harness / "project-memory.md").write_text("before\n", encoding="utf-8")
    logs = []

    def fake_generate_report(*args, **kwargs):
        (ctx.harness / "project-memory.md").write_text("after\n", encoding="utf-8")

    monkeypatch.setattr(runner_mod, "generate_report", fake_generate_report)
    runner = create_runner(MagicMock(), ctx, queue.Queue(), MissionState(), logs.append, BlockState())

    runner._generate_report()

    assert persistent.read_text(encoding="utf-8") == "after\n"
    assert "Project memory synced" in logs


def test_generate_report_saves_approved_mission_case(tmp_path, monkeypatch):
    ctx = _make_ctx(tmp_path)
    cases_path = tmp_path / "cases.jsonl"
    (ctx.harness / HARNESS_CASES_PATH_FILE).write_text(str(cases_path), encoding="utf-8")
    (ctx.harness / "tasks.json").write_text(
        json.dumps([{"id": "1", "title": "Task", "status": "completed"}]),
        encoding="utf-8",
    )
    (ctx.harness / "status.md").write_text("## Files\n- src/a.py\n", encoding="utf-8")
    (ctx.harness / "audit.md").write_text("## Verdict\nAPPROVED\n", encoding="utf-8")

    def fake_generate_report(*args, **kwargs):
        (ctx.harness / "mission-report.md").write_text("Approved report\n", encoding="utf-8")

    monkeypatch.setattr(runner_mod, "generate_report", fake_generate_report)
    logs = []
    runner = create_runner(MagicMock(), ctx, queue.Queue(), MissionState(), logs.append, BlockState())

    runner._generate_report()

    cases = read_cases(cases_path)
    assert len(cases) == 1
    assert cases[0]["task"] == "test task"
    assert cases[0]["files_changed"] == ["src/a.py"]
    assert "Mission case saved" in logs


def test_generate_report_syncs_generated_skills(tmp_path, monkeypatch):
    ctx = _make_ctx(tmp_path)
    skills_dir = tmp_path / "persistent-skills"
    (ctx.harness / HARNESS_SKILLS_PATH_FILE).write_text(str(skills_dir), encoding="utf-8")
    logs = []

    def fake_generate_report(*args, **kwargs):
        generated = ctx.harness / HARNESS_GENERATED_SKILLS_DIR
        generated.mkdir(parents=True, exist_ok=True)
        (generated / "runner-sync-skill.md").write_text(
            """---
skill_id: runner-sync-skill
name: Runner Sync Skill
version: 1
status: verified
source: mission-report
evidence: report generated a verified procedure
triggers:
  - runner sync
---
# Runner Sync Skill

## When To Use
Use when report output should promote a verified procedure.

## Procedure
1. Write a verified skill in generated-skills.

## Required Verification
- Confirm the skill is copied and indexed.

## Evidence
- mission-report.md.

## Risks
- Unverified skills should not be promoted.
""",
            encoding="utf-8",
        )

    monkeypatch.setattr(runner_mod, "generate_report", fake_generate_report)
    runner = create_runner(MagicMock(), ctx, queue.Queue(), MissionState(), logs.append, BlockState())

    runner._generate_report()

    records = read_skill_index(skills_dir.parent / "skills.jsonl")
    assert (skills_dir / "runner-sync-skill.md").is_file()
    assert any(record["skill_id"] == "runner-sync-skill" for record in records)
    assert "Verified skills synced: 1" in logs


# --- commit_task ---


def test_commit_task_approved(tmp_path, monkeypatch):
    ctx = _make_ctx(tmp_path)
    harness = ctx.harness
    (harness / "audit.md").write_text("APPROVED\n", encoding="utf-8")
    tasks = [{"id": "T1", "title": "t", "status": "pending"}]
    (harness / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")

    runner = _make_runner(tmp_path, monkeypatch, ctx=ctx)
    staged = []
    monkeypatch.setattr(hitl_mod, "stage_task_files", lambda h: staged.append(True))
    monkeypatch.setattr(BurstRunner, "compact_context", lambda *a, **kw: None)

    runner.hitl.commit_task(0, "T1", "t")

    updated = json.loads((harness / "tasks.json").read_text(encoding="utf-8"))
    assert updated[0]["status"] == "completed"
    assert staged == [True]


def test_commit_task_minor_changes(tmp_path, monkeypatch):
    ctx = _make_ctx(tmp_path)
    harness = ctx.harness
    (harness / "audit.md").write_text("MINOR_CHANGES\n", encoding="utf-8")
    tasks = [{"id": "T1", "title": "t", "status": "pending"}]
    (harness / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")

    reimplement_called = []
    def spy_reimplement(self, tid, ttitle, feedback):
        reimplement_called.append(tid)
    monkeypatch.setattr(HitlReviewer, "run_reimplement", spy_reimplement)
    monkeypatch.setattr(hitl_mod, "stage_task_files", lambda h: None)
    monkeypatch.setattr(BurstRunner, "compact_context", lambda *a, **kw: None)

    runner = _make_runner(tmp_path, monkeypatch, ctx=ctx)
    runner.hitl.commit_task(0, "T1", "t")

    assert reimplement_called == ["T1"]
    updated = json.loads((harness / "tasks.json").read_text(encoding="utf-8"))
    assert updated[0]["status"] == "completed"


def test_commit_task_blocked_skips(tmp_path, monkeypatch):
    ctx = _make_ctx(tmp_path)
    harness = ctx.harness
    tasks = [{"id": "T1", "title": "t", "status": "pending"}]
    (harness / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")

    blocked = BlockState()
    blocked.reason = BlockReason(BlockKind.TIMEOUT, phase="some_error")
    runner = _make_runner(tmp_path, monkeypatch, ctx=ctx, blocked=blocked)

    runner.hitl.commit_task(0, "T1", "t")

    updated = json.loads((harness / "tasks.json").read_text(encoding="utf-8"))
    assert updated[0]["status"] == "failed"


def test_commit_task_changes_requested_goes_hitl(tmp_path, monkeypatch):
    ctx = _make_ctx(tmp_path)
    harness = ctx.harness
    (harness / "audit.md").write_text("CHANGES_REQUESTED\n", encoding="utf-8")
    tasks = [{"id": "T1", "title": "t", "status": "pending"}]
    (harness / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")

    hitl_called = []
    def spy_hitl(self, idx, tid, ttitle):
        hitl_called.append(tid)
    monkeypatch.setattr(HitlReviewer, "hitl_review_loop", spy_hitl)

    runner = _make_runner(tmp_path, monkeypatch, ctx=ctx)
    runner.hitl.commit_task(0, "T1", "t")

    assert hitl_called == ["T1"]


def test_commit_task_approved_manual_gate_waits(tmp_path, monkeypatch):
    ctx = _make_ctx(tmp_path)
    harness = ctx.harness
    (harness / "audit.md").write_text("APPROVED\n", encoding="utf-8")
    (harness / "_gate_mode").write_text("manual", encoding="utf-8")
    tasks = [{"id": "T1", "title": "t", "status": "pending"}]
    (harness / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")

    wait_called = []
    def spy_wait(self, tid, ttitle):
        wait_called.append(tid)
        return True
    monkeypatch.setattr(HitlReviewer, "wait_approval", spy_wait)
    monkeypatch.setattr(hitl_mod, "stage_task_files", lambda h: None)
    monkeypatch.setattr(BurstRunner, "compact_context", lambda *a, **kw: None)

    runner = _make_runner(tmp_path, monkeypatch, ctx=ctx)
    runner.hitl.commit_task(0, "T1", "t")

    assert wait_called == ["T1"]
    updated = json.loads((harness / "tasks.json").read_text(encoding="utf-8"))
    assert updated[0]["status"] == "completed"


# --- wait_approval ---


def test_wait_approval_approve(tmp_path, monkeypatch):
    runner = _make_runner(tmp_path, monkeypatch)
    runner.command_queue.put({"cmd": "approve"})
    result = runner.hitl.wait_approval("T1", "Task 1")
    assert result is True
    assert runner.mission_state.waiting_approval is None
    events = read_events(runner.ctx.harness)
    assert [e["action"] for e in events] == ["waiting_approval", "approve"]


def test_wait_approval_reject(tmp_path, monkeypatch):
    runner = _make_runner(tmp_path, monkeypatch)
    runner.command_queue.put({"cmd": "reject", "reason": "bad code"})
    result = runner.hitl.wait_approval("T1", "Task 1")
    assert result is False
    assert "USER_REJECTED" in runner.blocked.value
    assert "bad code" in runner.blocked.value


def test_wait_approval_reject_no_reason(tmp_path, monkeypatch):
    runner = _make_runner(tmp_path, monkeypatch)
    runner.command_queue.put({"cmd": "reject"})
    result = runner.hitl.wait_approval("T1", "Task 1")
    assert result is False
    assert "USER_REJECTED" in runner.blocked.value


def test_wait_approval_abort(tmp_path, monkeypatch):
    runner = _make_runner(tmp_path, monkeypatch)
    runner.command_queue.put({"cmd": "abort"})
    result = runner.hitl.wait_approval("T1", "Task 1")
    assert result is False
    assert runner.blocked.value == "user_abort"


def test_wait_approval_gate_then_approve(tmp_path, monkeypatch):
    runner = _make_runner(tmp_path, monkeypatch)
    harness = runner.ctx.harness
    runner.command_queue.put({"cmd": "gate", "mode": "manual"})
    runner.command_queue.put({"cmd": "approve"})
    result = runner.hitl.wait_approval("T1", "Task 1")
    assert result is True
    assert (harness / "_gate_mode").read_text(encoding="utf-8") == "manual"


def test_wait_approval_pause_resume_approve(tmp_path, monkeypatch):
    runner = _make_runner(tmp_path, monkeypatch)
    runner.command_queue.put({"cmd": "pause"})
    runner.command_queue.put({"cmd": "resume"})
    runner.command_queue.put({"cmd": "approve"})
    result = runner.hitl.wait_approval("T1", "Task 1")
    assert result is True


def test_wait_approval_pause_abort(tmp_path, monkeypatch):
    runner = _make_runner(tmp_path, monkeypatch)
    runner.command_queue.put({"cmd": "pause"})
    runner.command_queue.put({"cmd": "abort"})
    result = runner.hitl.wait_approval("T1", "Task 1")
    assert result is False
    assert runner.blocked.value == "user_abort"


# --- run_reimplement ---


def test_run_reimplement_with_feedback(tmp_path, monkeypatch):
    ctx = _make_ctx(tmp_path)
    runner = _make_runner(tmp_path, monkeypatch, ctx=ctx)

    run_calls = []
    def spy_run(self_pr, config, variables, **kw):
        run_calls.append((config.name, variables.get("USER_FEEDBACK", "")))
    monkeypatch.setattr(PhaseRunner, "run", spy_run)

    runner.hitl.run_reimplement("T1", "Task 1", "fix the bug")

    assert len(run_calls) == 1
    assert "fix the bug" in run_calls[0][1]


def test_run_reimplement_no_feedback(tmp_path, monkeypatch):
    ctx = _make_ctx(tmp_path)
    runner = _make_runner(tmp_path, monkeypatch, ctx=ctx)

    run_calls = []
    def spy_run(self_pr, config, variables, **kw):
        run_calls.append((config.name, variables.get("USER_FEEDBACK", "")))
    monkeypatch.setattr(PhaseRunner, "run", spy_run)

    runner.hitl.run_reimplement("T1", "Task 1", "")

    assert len(run_calls) == 1
    assert "No additional user feedback" in run_calls[0][1]


# --- run_implement_bursts ---


def test_run_implement_bursts_no_plan(tmp_path, monkeypatch):
    ctx = _make_ctx(tmp_path)
    runner = _make_runner(tmp_path, monkeypatch, ctx=ctx)

    run_calls = []
    def spy_run(self_pr, config, variables, **kw):
        run_calls.append(config.name)
        return "ok"
    monkeypatch.setattr(PhaseRunner, "run", spy_run)

    runner.burst.run_implement_bursts("T1", "Task 1")

    assert run_calls == ["implement"]


def test_run_implement_bursts_with_steps(tmp_path, monkeypatch):
    ctx = _make_ctx(tmp_path)
    harness = ctx.harness
    plan_text = "# Plan\n## Steps\n### 1. Create module\nDetails here\n### 2. Add tests\nMore details\n"
    (harness / "plan.md").write_text(plan_text, encoding="utf-8")

    runner = _make_runner(tmp_path, monkeypatch, ctx=ctx)

    run_calls = []
    variable_calls = []
    def spy_run(self_pr, config, variables, **kw):
        run_calls.append(kw.get("phase_name_override", config.name))
        variable_calls.append(dict(variables))
        return MagicMock()
    monkeypatch.setattr(PhaseRunner, "run", spy_run)

    runner.burst.run_implement_bursts("T1", "Task 1")

    assert len(run_calls) == 2
    assert all("implement[T1]#" in c for c in run_calls)
    assert variable_calls[0]["PLAN_STEP"].startswith("### 1. Create module")
    assert "PROGRESS" in variable_calls[0]
    assert variable_calls[0]["TASK_COMPLEXITY"] == "M"
    assert "defaulted to M" in variable_calls[0]["TASK_COMPLEXITY_REASON"]
    assert variable_calls[1]["PLAN_STEP"].startswith("### 2. Add tests")
    assert "FINAL_INSTRUCTIONS" in variable_calls[1]
    assert "## Self-Verification" in variable_calls[1]["FINAL_INSTRUCTIONS"]
    assert "## Routing" in variable_calls[1]["FINAL_INSTRUCTIONS"]
    assert "deterministic_checks_run" in variable_calls[1]["FINAL_INSTRUCTIONS"]


def test_run_implement_bursts_phase_fails(tmp_path, monkeypatch):
    ctx = _make_ctx(tmp_path)
    harness = ctx.harness
    plan_text = "# Plan\n## Steps\n### 1. Step one\nDetails\n### 2. Step two\nDetails\n"
    (harness / "plan.md").write_text(plan_text, encoding="utf-8")

    runner = _make_runner(tmp_path, monkeypatch, ctx=ctx)

    call_count = [0]
    def spy_run(self_pr, config, variables, **kw):
        call_count[0] += 1
        return None
    monkeypatch.setattr(PhaseRunner, "run", spy_run)

    runner.burst.run_implement_bursts("T1", "Task 1")

    assert call_count[0] == 1


# --- compact_context ---


def test_compact_context_no_hot_file(tmp_path, monkeypatch):
    ctx = _make_ctx(tmp_path)
    runner = _make_runner(tmp_path, monkeypatch, ctx=ctx)
    runner.burst.compact_context()


def test_compact_context_output_too_short(tmp_path, monkeypatch):
    ctx = _make_ctx(tmp_path)
    harness = ctx.harness
    (harness / "context-hot.md").write_text("some context\n", encoding="utf-8")

    def fake_run_phase(*a, **kw):
        (harness / "_compact_tmp.md").write_text("short\n", encoding="utf-8")
        return MagicMock()
    monkeypatch.setattr("src.mission.burst_runner.agent_loop.run_phase", fake_run_phase)
    monkeypatch.setattr("src.mission.burst_runner.render_prompt", lambda *a, **kw: "prompt")
    monkeypatch.setattr("src.mission.burst_runner.make_tool_callback", lambda h: None)

    runner = _make_runner(tmp_path, monkeypatch, ctx=ctx)
    runner.burst.compact_context()

    assert (harness / "context-hot.md").exists()
    assert not (harness / "_compact_tmp.md").exists()


def test_compact_context_happy(tmp_path, monkeypatch):
    ctx = _make_ctx(tmp_path)
    harness = ctx.harness
    (harness / "context-hot.md").write_text("some hot context\n", encoding="utf-8")

    compact_output = "line1\nline2\nline3\nline4\n"

    def fake_run_phase(*a, **kw):
        (harness / "_compact_tmp.md").write_text(compact_output, encoding="utf-8")
        return MagicMock()
    monkeypatch.setattr("src.mission.burst_runner.agent_loop.run_phase", fake_run_phase)
    monkeypatch.setattr("src.mission.burst_runner.render_prompt", lambda *a, **kw: "prompt")
    monkeypatch.setattr("src.mission.burst_runner.make_tool_callback", lambda h: None)

    runner = _make_runner(tmp_path, monkeypatch, ctx=ctx)
    runner.burst.compact_context()

    assert not (harness / "context-hot.md").exists()
    assert not (harness / "_compact_tmp.md").exists()
    cold = (harness / "context-cold.md").read_text(encoding="utf-8")
    assert "line1" in cold


def test_compact_context_timeout_blocks(tmp_path, monkeypatch):
    ctx = _make_ctx(tmp_path)
    harness = ctx.harness
    (harness / "context-hot.md").write_text("context\n", encoding="utf-8")

    def fake_run_phase(*a, **kw):
        raise PhaseTimeout("timeout")
    monkeypatch.setattr("src.mission.burst_runner.agent_loop.run_phase", fake_run_phase)
    monkeypatch.setattr("src.mission.burst_runner.render_prompt", lambda *a, **kw: "prompt")
    monkeypatch.setattr("src.mission.burst_runner.make_tool_callback", lambda h: None)

    blocked = BlockState()
    runner = _make_runner(tmp_path, monkeypatch, ctx=ctx, blocked=blocked)
    runner.burst.compact_context()

    assert "compact" in blocked.value
    assert "timeout" in blocked.value


def test_compact_context_max_turns_blocks(tmp_path, monkeypatch):
    ctx = _make_ctx(tmp_path)
    harness = ctx.harness
    (harness / "context-hot.md").write_text("context\n", encoding="utf-8")

    def fake_run_phase(*a, **kw):
        raise MaxTurnsExceeded("max_turns")
    monkeypatch.setattr("src.mission.burst_runner.agent_loop.run_phase", fake_run_phase)
    monkeypatch.setattr("src.mission.burst_runner.render_prompt", lambda *a, **kw: "prompt")
    monkeypatch.setattr("src.mission.burst_runner.make_tool_callback", lambda h: None)

    blocked = BlockState()
    runner = _make_runner(tmp_path, monkeypatch, ctx=ctx, blocked=blocked)
    runner.burst.compact_context()

    assert "max_turns" in blocked.value


# --- _run_finalize ---


def test_run_finalize_no_merge_mode(tmp_path, monkeypatch):
    for mode in ("spec", "spec-plan"):
        ctx = _make_ctx(tmp_path, mode=mode)
        harness = ctx.harness
        tasks = [{"id": "T1", "title": "t", "status": "completed"}]
        (harness / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")

        merge_calls = []
        monkeypatch.setattr(runner_mod, "merge_to_develop", lambda b, l: merge_calls.append(b) or True)

        runner = _make_runner(tmp_path, monkeypatch, ctx=ctx)
        runner._run_finalize(1)

        assert merge_calls == []


def test_run_finalize_with_merge(tmp_path, monkeypatch):
    ctx = _make_ctx(tmp_path, mode="full")
    harness = ctx.harness
    tasks = [{"id": "T1", "title": "t", "status": "completed"}]
    (harness / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")

    runner = _make_runner(tmp_path, monkeypatch, ctx=ctx)
    merge_calls = []
    monkeypatch.setattr(runner_mod, "merge_to_develop", lambda b, l: merge_calls.append(b) or True)
    runner._run_finalize(1)

    assert len(merge_calls) == 1


def test_run_finalize_blocked_skips_merge(tmp_path, monkeypatch):
    ctx = _make_ctx(tmp_path, mode="full")
    harness = ctx.harness
    tasks = [{"id": "T1", "title": "t", "status": "failed"}]
    (harness / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")

    blocked = BlockState()
    blocked.reason = BlockReason(BlockKind.TIMEOUT, phase="some_error")
    runner = _make_runner(tmp_path, monkeypatch, ctx=ctx, blocked=blocked)
    merge_calls = []
    monkeypatch.setattr(runner_mod, "merge_to_develop", lambda b, l: merge_calls.append(b) or True)
    runner._run_finalize(0)

    assert merge_calls == []


def test_run_finalize_failed_tasks_logged(tmp_path, monkeypatch):
    ctx = _make_ctx(tmp_path, mode="full")
    harness = ctx.harness
    tasks = [
        {"id": "T1", "title": "t", "status": "completed"},
        {"id": "T2", "title": "t2", "status": "failed"},
    ]
    (harness / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")

    runner = _make_runner(tmp_path, monkeypatch, ctx=ctx)
    logged = []
    runner.log = lambda msg: logged.append(msg)
    monkeypatch.setattr(runner_mod, "merge_to_develop", lambda b, l: True)
    runner._run_finalize(1)

    assert any("partial" in m.lower() for m in logged)


# --- hitl_review_loop ---


def test_hitl_review_loop_skip(tmp_path, monkeypatch):
    ctx = _make_ctx(tmp_path)
    harness = ctx.harness
    (harness / "audit.md").write_text("CHANGES_REQUESTED\n", encoding="utf-8")
    tasks = [{"id": "T1", "title": "t", "status": "pending"}]
    (harness / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")

    runner = _make_runner(tmp_path, monkeypatch, ctx=ctx)
    runner.command_queue.put({"cmd": "skip"})

    runner.hitl.hitl_review_loop(0, "T1", "t")

    updated = json.loads((harness / "tasks.json").read_text(encoding="utf-8"))
    assert updated[0]["status"] == "failed"


def test_hitl_review_loop_force_approve(tmp_path, monkeypatch):
    ctx = _make_ctx(tmp_path)
    harness = ctx.harness
    (harness / "audit.md").write_text("CHANGES_REQUESTED\n", encoding="utf-8")
    tasks = [{"id": "T1", "title": "t", "status": "pending"}]
    (harness / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")

    monkeypatch.setattr(hitl_mod, "stage_task_files", lambda h: None)
    monkeypatch.setattr(BurstRunner, "compact_context", lambda *a, **kw: None)

    runner = _make_runner(tmp_path, monkeypatch, ctx=ctx)
    runner.command_queue.put({"cmd": "approve"})

    runner.hitl.hitl_review_loop(0, "T1", "t")

    updated = json.loads((harness / "tasks.json").read_text(encoding="utf-8"))
    assert updated[0]["status"] == "completed"


def test_hitl_review_loop_abort(tmp_path, monkeypatch):
    ctx = _make_ctx(tmp_path)
    harness = ctx.harness
    (harness / "audit.md").write_text("CHANGES_REQUESTED\n", encoding="utf-8")
    tasks = [{"id": "T1", "title": "t", "status": "pending"}]
    (harness / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")

    runner = _make_runner(tmp_path, monkeypatch, ctx=ctx)
    runner.command_queue.put({"cmd": "abort"})

    runner.hitl.hitl_review_loop(0, "T1", "t")

    assert runner.blocked.value == "user_abort"
    updated = json.loads((harness / "tasks.json").read_text(encoding="utf-8"))
    assert updated[0]["status"] == "failed"


def test_hitl_review_loop_retry_then_approved(tmp_path, monkeypatch):
    ctx = _make_ctx(tmp_path)
    harness = ctx.harness
    (harness / "audit.md").write_text("CHANGES_REQUESTED\n", encoding="utf-8")
    tasks = [{"id": "T1", "title": "t", "status": "pending"}]
    (harness / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")

    call_count = [0]
    def spy_run(self_pr, config, variables, **kw):
        call_count[0] += 1
        if config.name == "review":
            (harness / "audit.md").write_text("APPROVED\n", encoding="utf-8")
    monkeypatch.setattr(PhaseRunner, "run", spy_run)
    monkeypatch.setattr(hitl_mod, "stage_task_files", lambda h: None)
    monkeypatch.setattr(BurstRunner, "compact_context", lambda *a, **kw: None)
    monkeypatch.setattr(HitlReviewer, "run_reimplement", lambda *a, **kw: None)

    runner = _make_runner(tmp_path, monkeypatch, ctx=ctx)
    runner.command_queue.put({"cmd": "retry", "feedback": "fix it"})

    runner.hitl.hitl_review_loop(0, "T1", "t")

    updated = json.loads((harness / "tasks.json").read_text(encoding="utf-8"))
    assert updated[0]["status"] == "completed"
    events = read_events(harness)
    retry = next(e for e in events if e.get("action") == "retry")
    assert retry["feedback"] == "fix it"
    assert retry["retry_count"] == 1


# --- execute edge cases ---


def test_execute_explore_mode_skips_task_loop(tmp_path, monkeypatch):
    ctx = _make_ctx(tmp_path, mode="explore")

    phase_calls = []
    def spy_run(self_pr, config, variables, **kw):
        phase_calls.append(config.name)
    def spy_conv(self_pr, config, variables, get_input, **kw):
        phase_calls.append(config.name)
    monkeypatch.setattr(PhaseRunner, "run", spy_run)
    monkeypatch.setattr(PhaseRunner, "run_conversation", spy_conv)
    monkeypatch.setattr(BurstRunner, "compact_context", lambda *a, **kw: None)

    runner = _make_runner(tmp_path, monkeypatch, ctx=ctx)
    runner.execute()

    assert "research" in phase_calls
    assert "spec" not in phase_calls
    assert "implement" not in phase_calls


def test_execute_no_tasks_json_errors(tmp_path, monkeypatch):
    ctx = _make_ctx(tmp_path)

    def spy_run(self_pr, config, variables, **kw):
        pass
    def spy_conv(self_pr, config, variables, get_input, **kw):
        pass
    monkeypatch.setattr(PhaseRunner, "run", spy_run)
    monkeypatch.setattr(PhaseRunner, "run_conversation", spy_conv)

    logged = []
    runner = _make_runner(tmp_path, monkeypatch, ctx=ctx)
    runner.log = lambda msg: logged.append(msg)
    runner.execute()

    assert any("tasks.json" in m for m in logged)


def test_execute_skips_completed_tasks(tmp_path, monkeypatch):
    ctx = _make_ctx(tmp_path)
    harness = ctx.harness
    tasks = [
        {"id": "T1", "title": "done", "status": "completed"},
        {"id": "T2", "title": "todo", "status": "pending"},
    ]
    (harness / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")

    phase_calls = []
    def spy_run(self_pr, config, variables, **kw):
        override = kw.get("phase_name_override", config.name)
        phase_calls.append(override)
    def spy_conv(self_pr, config, variables, get_input, **kw):
        phase_calls.append(config.name)
    monkeypatch.setattr(PhaseRunner, "run", spy_run)
    monkeypatch.setattr(PhaseRunner, "run_conversation", spy_conv)
    monkeypatch.setattr(BurstRunner, "compact_context", lambda *a, **kw: None)
    monkeypatch.setattr(HitlReviewer, "commit_task", lambda *a, **kw: None)

    runner = _make_runner(tmp_path, monkeypatch, ctx=ctx)
    runner.execute()

    task_impl = [p for p in phase_calls if "T1" in p]
    assert task_impl == []
    task_impl2 = [p for p in phase_calls if "T2" in p]
    assert len(task_impl2) > 0


def test_task_loop_abort_stops_all(tmp_path, monkeypatch):
    ctx = _make_ctx(tmp_path)
    harness = ctx.harness
    tasks = [
        {"id": "T1", "title": "t1", "status": "pending"},
        {"id": "T2", "title": "t2", "status": "pending"},
    ]
    (harness / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")

    def block_on_t1(self_pr, config, variables, **kw):
        if variables.get("TASK_ID") == "T1":
            self_pr.blocked.reason = BlockReason(BlockKind.USER_ABORT)
    def spy_conv(self_pr, config, variables, get_input, **kw):
        pass
    monkeypatch.setattr(PhaseRunner, "run", block_on_t1)
    monkeypatch.setattr(PhaseRunner, "run_conversation", spy_conv)
    monkeypatch.setattr(BurstRunner, "compact_context", lambda *a, **kw: None)

    blocked = BlockState()
    runner = _make_runner(tmp_path, monkeypatch, ctx=ctx, blocked=blocked)
    runner.execute()

    assert blocked.value == "user_abort"
