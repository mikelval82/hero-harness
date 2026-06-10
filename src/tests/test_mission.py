import sys
import argparse
import json
import os
import queue
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

from src import cli as mission

from src.cli import parse_args, resolve_args
from src.core.state import update_state, _apply_gate_change
from src.mission.signals import check_signals
from src.mission.human_input import _parse_stdin_line
from src.core.block_state import BlockState, BlockKind, BlockReason
from src.core.gate import check_gate, parse_plan_steps
from src.core.git import (
    detect_base_branch, ensure_git_identity, setup_branch, setup_git,
    ensure_develop, merge_to_develop, final_commit,
)
from src.core.notification import notify
from src.mission.reporting import _consolidate_tasks, build_code_graph, notify_result
from src.mission.phase_runner import PhaseRunner
from src.mission.runner import MissionRunner, create_runner
from src.harness.harness_utils import sanitize_name as _sanitize_name, setup_harness
from src.harness.tasks import (
    parse_status_files as _parse_status_files,
    update_task as _update_task,
    task_summary as _task_summary,
    is_mission_abort as _is_mission_abort,
    audit_verdict as _audit_verdict,
    stage_task_files,
)
from src.harness.telemetry import read_events, write_phase_event
from src.integrations.notifier import PROJECT_COLORS, compute_notify_prefix
from src.agent.loop import PhaseResult, PhaseTimeout
from src.core.context import DEFAULT_TOOLS, PHASE_REGISTRY, MissionContext, PhaseConfig
from src.integrations.telegram_listener import MissionState
import src.agent.loop as _al
from src.mission import reporting as reporting_mod
from src.mission import phase_runner as phase_runner_mod
from src.mission import runner as mission_runner_mod
from src.mission.burst_runner import BurstRunner
from src.mission.hitl import HitlReviewer
import src.mission.hitl as hitl_mod

import pytest


# --- parse_args tests ---


def test_mission_module_does_not_reexport_runtime_collaborators():
    accidental_exports = [
        "setup_harness",
        "register_mission",
        "unregister_mission",
        "list_missions",
        "ensure_develop",
        "setup_git",
        "final_commit",
        "notify",
        "notify_result",
        "build_code_graph",
        "_consolidate_tasks",
        "update_state",
        "_apply_gate_change",
        "check_signals",
        "_parse_stdin_line",
        "stage_task_files",
        "BlockState",
        "MissionContext",
        "PhaseRunner",
        "MissionRunner",
        "PHASE_REGISTRY",
    ]

    assert [name for name in accidental_exports if hasattr(mission, name)] == []


def test_parse_args_defaults():
    args = parse_args([])
    assert args.task is None
    assert args.branch is None
    assert args.no_grill is False
    assert args.gate is False
    assert args.mode == "full"
    assert args.task_file is None
    assert args.max_tasks == mission.MAX_TASKS


def test_parse_args_max_tasks():
    args = parse_args(["--max-tasks", "5", "t"])
    assert args.max_tasks == 5


def test_parse_args_task_only():
    args = parse_args(["my task"])
    assert args.task == "my task"
    assert args.branch is None


def test_parse_args_task_and_branch_positional():
    args = parse_args(["my task", "feat-x"])
    assert args.task == "my task"
    assert args.branch == "feat-x"


def test_parse_args_no_grill_flag():
    args = parse_args(["--no-grill", "t"])
    assert args.no_grill is True


def test_parse_args_gate_flag():
    args = parse_args(["--gate", "t"])
    assert args.gate is True


def test_parse_args_spec_only():
    args = parse_args(["--spec-only", "t"])
    assert args.mode == "spec"


def test_parse_args_spec_plan():
    args = parse_args(["--spec-plan", "t"])
    assert args.mode == "spec-plan"


def test_parse_args_mode_explicit():
    args = parse_args(["--mode", "explore", "t"])
    assert args.mode == "explore"


def test_parse_args_mode_overrides_partial_aliases():
    args = parse_args(["--mode", "focused", "--spec-only", "--spec-plan", "t"])
    assert args.mode == "focused"


def test_parse_args_partial_aliases_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        parse_args(["--spec-only", "--spec-plan", "t"])


def test_parse_args_plan_mode_removed():
    with pytest.raises(SystemExit):
        parse_args(["--mode", "plan", "t"])


def test_parse_args_plan_only_removed():
    with pytest.raises(SystemExit):
        parse_args(["--plan-only", "t"])


def test_parse_args_branch_flag_overrides_positional():
    args = parse_args(["task", "feat-x", "--branch", "feat-y"])
    assert args.branch == "feat-y"


def test_parse_args_task_file():
    args = parse_args(["--task-file", "some/path", "t"])
    assert args.task_file == "some/path"


def test_parse_args_cleanup_attrs():
    args = parse_args(["t"])
    with pytest.raises(AttributeError):
        _ = args.plan_only
    with pytest.raises(AttributeError):
        _ = args.spec_only
    with pytest.raises(AttributeError):
        _ = args.spec_plan
    with pytest.raises(AttributeError):
        _ = args.branch_pos
    with pytest.raises(AttributeError):
        _ = args.branch_flag


def test_parse_args_mode_focused():
    args = parse_args(["--mode", "focused", "t"])
    assert args.mode == "focused"


def test_parse_args_mode_hotfix():
    args = parse_args(["--mode", "hotfix", "t"])
    assert args.mode == "hotfix"


def test_parse_args_mode_spec():
    args = parse_args(["--mode", "spec", "t"])
    assert args.mode == "spec"


def test_parse_args_mode_spec_plan():
    args = parse_args(["--mode", "spec-plan", "t"])
    assert args.mode == "spec-plan"


# --- _parse_stdin_line tests ---


def test_parse_stdin_line_empty():
    assert _parse_stdin_line("") is None
    assert _parse_stdin_line("   ") is None


def test_parse_stdin_line_simple_commands():
    assert _parse_stdin_line("/approve") == {"cmd": "approve"}
    assert _parse_stdin_line("/skip") == {"cmd": "skip"}
    assert _parse_stdin_line("/abort") == {"cmd": "abort"}
    assert _parse_stdin_line("/pause") == {"cmd": "pause"}
    assert _parse_stdin_line("/resume") == {"cmd": "resume"}
    assert _parse_stdin_line("/done") == {"cmd": "done"}


def test_parse_stdin_line_retry_no_feedback():
    assert _parse_stdin_line("/retry") == {"cmd": "retry", "feedback": ""}


def test_parse_stdin_line_retry_with_feedback():
    result = _parse_stdin_line("/retry fix the bug")
    assert result == {"cmd": "retry", "feedback": "fix the bug"}


def test_parse_stdin_line_gate_on():
    assert _parse_stdin_line("/gate on") == {"cmd": "gate", "mode": "manual"}


def test_parse_stdin_line_gate_off():
    assert _parse_stdin_line("/gate off") == {"cmd": "gate", "mode": "auto"}


def test_parse_stdin_line_gate_invalid_arg():
    result = _parse_stdin_line("/gate foo")
    assert result == {"cmd": "answer", "text": "/gate foo"}


def test_parse_stdin_line_plain_text():
    assert _parse_stdin_line("hello world") == {"cmd": "answer", "text": "hello world"}


# --- resolve_args tests ---


def test_resolve_args_task_file_valid(tmp_path):
    task_file = tmp_path / "task.txt"
    task_file.write_text("  build the feature  \n", encoding="utf-8")
    args = argparse.Namespace(task=None, task_file=str(task_file), branch="main")
    resolve_args(args)
    assert args.task == "build the feature"


def test_resolve_args_task_file_missing():
    args = argparse.Namespace(task=None, task_file="/nonexistent/task.txt", branch="main")
    with pytest.raises(SystemExit) as exc:
        resolve_args(args)
    assert exc.value.code == 1


def test_resolve_args_interactive_fallback(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "interactive task")
    args = argparse.Namespace(task=None, task_file=None, branch="main")
    resolve_args(args)
    assert args.task == "interactive task"


def test_resolve_args_no_task_exits(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "")
    args = argparse.Namespace(task=None, task_file=None, branch="main")
    with pytest.raises(SystemExit) as exc:
        resolve_args(args)
    assert exc.value.code == 1


def test_resolve_args_branch_auto_feature(monkeypatch):
    args = argparse.Namespace(task="modernize graph", task_file=None, branch=None)
    resolve_args(args)
    assert args.branch == "feature/modernizegraph"


def test_resolve_args_task_file_whitespace_only(tmp_path, monkeypatch):
    task_file = tmp_path / "empty.txt"
    task_file.write_text("   \n  \n", encoding="utf-8")
    monkeypatch.setattr("builtins.input", lambda _: "")
    args = argparse.Namespace(task=None, task_file=str(task_file), branch="main")
    with pytest.raises(SystemExit) as exc:
        resolve_args(args)
    assert exc.value.code == 1


# --- fixtures ---


@pytest.fixture
def reset_blocked():
    yield


@pytest.fixture
def save_env():
    old = os.environ.get("CLAUDE_HARNESS")
    yield
    if old is None:
        os.environ.pop("CLAUDE_HARNESS", None)
    else:
        os.environ["CLAUDE_HARNESS"] = old


# --- detect_base_branch tests ---


def test_detect_base_branch_origin_head(monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        m = MagicMock()
        m.returncode = 0
        m.stdout = "refs/remotes/origin/develop\n"
        return m

    monkeypatch.setattr("src.core.git.subprocess.run", fake_run)
    assert detect_base_branch() == "develop"
    assert len(calls) == 1


def test_detect_base_branch_fallback_main(monkeypatch):
    call_count = [0]

    def fake_run(cmd, **kw):
        call_count[0] += 1
        m = MagicMock()
        if call_count[0] == 1:
            m.returncode = 1
            m.stdout = ""
        else:
            m.returncode = 0
        return m

    monkeypatch.setattr("src.core.git.subprocess.run", fake_run)
    assert detect_base_branch() == "main"
    assert call_count[0] == 2


def test_detect_base_branch_fallback_master(monkeypatch):
    call_count = [0]

    def fake_run(cmd, **kw):
        call_count[0] += 1
        m = MagicMock()
        if call_count[0] <= 2:
            m.returncode = 1
        else:
            m.returncode = 0
        m.stdout = ""
        return m

    monkeypatch.setattr("src.core.git.subprocess.run", fake_run)
    assert detect_base_branch() == "master"
    assert call_count[0] == 3


def test_detect_base_branch_all_fail(monkeypatch):
    def fake_run(cmd, **kw):
        m = MagicMock()
        m.returncode = 1
        m.stdout = ""
        return m

    monkeypatch.setattr("src.core.git.subprocess.run", fake_run)
    assert detect_base_branch() == "main"


# --- ensure_git_identity tests ---


def test_ensure_git_identity_already_set(monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        m = MagicMock()
        m.returncode = 0
        return m

    monkeypatch.setattr("src.core.git.subprocess.run", fake_run)
    ensure_git_identity()
    assert len(calls) == 1


def test_ensure_git_identity_sets_from_env(monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        m = MagicMock()
        m.returncode = 1 if len(calls) == 1 else 0
        return m

    monkeypatch.setattr("src.core.git.subprocess.run", fake_run)
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Test User")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.com")
    ensure_git_identity()
    assert len(calls) == 3
    assert calls[1] == ["git", "config", "--global", "user.name", "Test User"]
    assert calls[2] == ["git", "config", "--global", "user.email", "test@example.com"]


def test_ensure_git_identity_raises_without_env(monkeypatch):
    def fake_run(cmd, **kw):
        m = MagicMock()
        m.returncode = 1
        return m

    monkeypatch.setattr("src.core.git.subprocess.run", fake_run)
    monkeypatch.delenv("GIT_AUTHOR_NAME", raising=False)
    monkeypatch.delenv("GIT_AUTHOR_EMAIL", raising=False)
    with pytest.raises(RuntimeError, match="GIT_AUTHOR_NAME"):
        ensure_git_identity()


# --- setup_branch tests ---


def test_setup_branch_created(monkeypatch):
    def fake_run(cmd, **kw):
        m = MagicMock()
        m.returncode = 0
        return m

    monkeypatch.setattr("src.core.git.subprocess.run", fake_run)
    assert setup_branch("feat-x") == "created"


def test_setup_branch_existing(monkeypatch):
    call_count = [0]

    def fake_run(cmd, **kw):
        call_count[0] += 1
        m = MagicMock()
        m.returncode = 1 if call_count[0] == 1 else 0
        return m

    monkeypatch.setattr("src.core.git.subprocess.run", fake_run)
    assert setup_branch("feat-x") == "existing"


# --- setup_git tests ---


def test_setup_git_delegates(monkeypatch):
    identity_called = [False]
    branch_called = [False]

    def fake_identity():
        identity_called[0] = True

    def fake_branch(b):
        branch_called[0] = True
        return "created"

    monkeypatch.setattr("src.core.git.ensure_git_identity", fake_identity)
    monkeypatch.setattr("src.core.git.setup_branch", fake_branch)
    result = setup_git("feat-x")
    assert identity_called[0]
    assert branch_called[0]
    assert result == "created"


# --- _sanitize_name tests ---


def test_sanitize_name_basic():
    assert _sanitize_name("my-project") == "my-project"


def test_sanitize_name_slashes():
    assert _sanitize_name("feat/login") == "feat-login"


def test_sanitize_name_special_chars():
    assert _sanitize_name("hello@world#!") == "helloworld"


def test_sanitize_name_max_len():
    assert _sanitize_name("abcdefghij", max_len=5) == "abcde"


def test_sanitize_name_empty():
    assert _sanitize_name("") == ""


# --- setup_harness tests ---


def test_setup_harness_basic(tmp_path, save_env, monkeypatch):
    monkeypatch.setattr("src.harness.harness_utils.Path.home", staticmethod(lambda: tmp_path))
    result = setup_harness("feat-x", False, cwd=tmp_path)
    assert result["branch_safe"] == "feat-x"
    assert result["project_name"] == _sanitize_name(tmp_path.name)
    assert result["mission_tag"] == f"{result['project_name']}:feat-x"
    assert result["harness"].exists()
    assert (result["harness"] / "_project_dir").read_text(encoding="utf-8") == str(tmp_path.resolve())
    assert (result["harness"] / "_gate_mode").read_text(encoding="utf-8") == "auto"
    assert (result["harness"] / "project-memory.md").is_file()
    assert (result["harness"] / "_project_memory_path").is_file()
    assert (result["harness"] / "retrieved-cases.md").is_file()
    assert (result["harness"] / "_project_cases_path").is_file()
    assert (result["harness"] / "retrieved-skills.md").is_file()
    assert (result["harness"] / "_project_skills_path").is_file()
    assert (result["harness"] / "generated-skills").is_dir()
    assert Path(result["project_memory_path"]).is_file()
    assert Path(result["project_memory_harness"]) == result["harness"] / "project-memory.md"
    assert Path(result["project_cases_path"]).is_file()
    assert Path(result["retrieved_cases_harness"]) == result["harness"] / "retrieved-cases.md"
    assert Path(result["project_skills_path"]).is_dir()
    assert Path(result["retrieved_skills_harness"]) == result["harness"] / "retrieved-skills.md"
    assert Path(result["generated_skills_harness"]) == result["harness"] / "generated-skills"
    assert os.environ["CLAUDE_HARNESS"] == result["harness_win"]


def test_setup_harness_gate_enabled(tmp_path, save_env, monkeypatch):
    monkeypatch.setattr("src.harness.harness_utils.Path.home", staticmethod(lambda: tmp_path))
    result = setup_harness("feat-x", True, cwd=tmp_path)
    assert (result["harness"] / "_gate_mode").read_text(encoding="utf-8") == "manual"


def test_setup_harness_preexisting_dir(tmp_path, save_env, monkeypatch):
    monkeypatch.setattr("src.harness.harness_utils.Path.home", staticmethod(lambda: tmp_path))
    harness_dir = tmp_path / ".harness" / _sanitize_name(tmp_path.name) / "feat-x"
    harness_dir.mkdir(parents=True)
    (harness_dir / "old_file.txt").write_text("old", encoding="utf-8")
    result = setup_harness("feat-x", False, cwd=tmp_path)
    assert not (result["harness"] / "old_file.txt").exists()
    assert (result["harness"] / "_project_dir").exists()


def test_setup_harness_resume_preserves_staged_project_memory(tmp_path, save_env, monkeypatch):
    monkeypatch.setattr("src.harness.harness_utils.Path.home", staticmethod(lambda: tmp_path))
    first = setup_harness("feat-x", False, cwd=tmp_path)
    (first["harness"] / "tasks.json").write_text("[]", encoding="utf-8")
    (first["harness"] / "project-memory.md").write_text("mission-local memory\n", encoding="utf-8")
    (first["harness"] / "retrieved-cases.md").write_text("mission-local cases\n", encoding="utf-8")
    (first["harness"] / "retrieved-skills.md").write_text("mission-local skills\n", encoding="utf-8")

    resumed = setup_harness("feat-x", False, cwd=tmp_path, resume=True)

    assert resumed["harness"] == first["harness"]
    assert (resumed["harness"] / "project-memory.md").read_text(encoding="utf-8") == "mission-local memory\n"
    assert (resumed["harness"] / "retrieved-cases.md").read_text(encoding="utf-8") == "mission-local cases\n"
    assert (resumed["harness"] / "retrieved-skills.md").read_text(encoding="utf-8") == "mission-local skills\n"


def test_setup_harness_claude_home_path(tmp_path, save_env, monkeypatch):
    monkeypatch.setattr("src.harness.harness_utils.Path.home", staticmethod(lambda: tmp_path))
    claude_dir = tmp_path / ".claude" / "fakedir"
    claude_dir.mkdir(parents=True)
    result = setup_harness("feat-x", False, cwd=claude_dir)
    assert str(tmp_path / ".harness") in str(result["harness"])


# --- compute_notify_prefix tests ---


def test_compute_notify_prefix_deterministic():
    a = compute_notify_prefix("myproject")
    b = compute_notify_prefix("myproject")
    assert a == b
    assert "myproject" in a
    assert any(e in a for e in PROJECT_COLORS)


# --- update_state tests ---


def test_update_state_writes_json(tmp_path):
    harness = tmp_path / "harness"
    harness.mkdir()
    (harness / "_gate_mode").write_text("auto", encoding="utf-8")
    update_state("brainstorm", harness, task_id="1", task_title="test", mode="full")
    data = json.loads((harness / "_state.json").read_text(encoding="utf-8"))
    assert data["phase"] == "brainstorm"
    assert data["task_id"] == "1"
    assert data["mode"] == "full"
    assert data["gate"] == "auto"


def test_update_state_updates_mission_state(tmp_path):
    harness = tmp_path / "harness"
    harness.mkdir()
    (harness / "_gate_mode").write_text("auto", encoding="utf-8")
    ms = MissionState()
    update_state("spec", harness, mission_state=ms, task_id="2", task_title="t2",
                 task_num=1, task_count=3, completed=0, mode="full")
    assert ms.phase == "spec"
    assert ms.task_id == "2"
    assert ms.task_num == 1
    assert ms.task_count == 3


def test_update_state_none_mission_state(tmp_path):
    harness = tmp_path / "harness"
    harness.mkdir()
    (harness / "_gate_mode").write_text("auto", encoding="utf-8")
    update_state("plan", harness, mission_state=None, task_id="3")
    data = json.loads((harness / "_state.json").read_text(encoding="utf-8"))
    assert data["phase"] == "plan"


# --- _apply_gate_change tests ---


def test_apply_gate_change_writes_and_updates(tmp_path):
    harness = tmp_path / "harness"
    harness.mkdir()
    ms = MissionState()
    _apply_gate_change("manual", harness, ms)
    assert (harness / "_gate_mode").read_text(encoding="utf-8") == "manual"
    assert ms.gate == "manual"


def test_apply_gate_change_none_mission_state(tmp_path):
    harness = tmp_path / "harness"
    harness.mkdir()
    _apply_gate_change("auto", harness, None)
    assert (harness / "_gate_mode").read_text(encoding="utf-8") == "auto"


# --- check_signals tests ---


def test_check_signals_empty_queue(tmp_path, reset_blocked, monkeypatch):
    monkeypatch.setattr("src.mission.signals.notify", lambda msg: None)
    q = queue.Queue()
    harness = tmp_path / "harness"
    harness.mkdir()
    blocked = BlockState()
    assert check_signals(q, harness, None, blocked) is True


def test_check_signals_abort(tmp_path, reset_blocked, monkeypatch):
    monkeypatch.setattr("src.mission.signals.notify", lambda msg: None)
    q = queue.Queue()
    q.put({"cmd": "abort"})
    harness = tmp_path / "harness"
    harness.mkdir()
    blocked = BlockState()
    assert check_signals(q, harness, None, blocked) is False
    assert blocked.value == "user_abort"


def test_check_signals_pause_resume(tmp_path, reset_blocked, monkeypatch):
    monkeypatch.setattr("src.mission.signals.notify", lambda msg: None)
    q = queue.Queue()
    q.put({"cmd": "pause"})
    q.put({"cmd": "resume"})
    harness = tmp_path / "harness"
    harness.mkdir()
    blocked = BlockState()
    assert check_signals(q, harness, None, blocked) is True


def test_check_signals_pause_abort(tmp_path, reset_blocked, monkeypatch):
    monkeypatch.setattr("src.mission.signals.notify", lambda msg: None)
    q = queue.Queue()
    q.put({"cmd": "pause"})
    q.put({"cmd": "abort"})
    harness = tmp_path / "harness"
    harness.mkdir()
    blocked = BlockState()
    assert check_signals(q, harness, None, blocked) is False
    assert blocked.value == "user_abort"


def test_check_signals_gate(tmp_path, reset_blocked, monkeypatch):
    monkeypatch.setattr("src.mission.signals.notify", lambda msg: None)
    q = queue.Queue()
    q.put({"cmd": "gate", "mode": "manual"})
    harness = tmp_path / "harness"
    harness.mkdir()
    ms = MissionState()
    blocked = BlockState()
    assert check_signals(q, harness, ms, blocked) is True
    assert (harness / "_gate_mode").read_text(encoding="utf-8") == "manual"
    assert ms.gate == "manual"


def test_check_signals_non_signal_requeued(tmp_path, reset_blocked, monkeypatch):
    monkeypatch.setattr("src.mission.signals.notify", lambda msg: None)
    requeued = []

    class FakeQueue:
        def __init__(self):
            self._items = [{"cmd": "approve"}]
            self._calls = 0

        def get_nowait(self):
            self._calls += 1
            if self._calls == 1:
                return self._items.pop(0)
            raise queue.Empty

        def get(self, timeout=None):
            raise queue.Empty

        def put(self, item):
            requeued.append(item)

    harness = tmp_path / "harness"
    harness.mkdir()
    fq = FakeQueue()
    blocked = BlockState()
    assert check_signals(fq, harness, None, blocked) is True
    assert len(requeued) == 1
    assert requeued[0]["cmd"] == "approve"


def test_check_signals_pause_defers_non_pause_commands(tmp_path, reset_blocked, monkeypatch):
    monkeypatch.setattr("src.mission.signals.notify", lambda msg: None)

    class RequeueingQueue:
        def __init__(self):
            self._items = [{"cmd": "pause"}, {"cmd": "approve"}, {"cmd": "resume"}]
            self.gets = 0
            self.requeued = []

        def get_nowait(self):
            self.gets += 1
            if self.gets > 4:
                raise AssertionError("deferred command was read again in the same tick")
            if self._items:
                return self._items.pop(0)
            raise queue.Empty

        def get(self, timeout=None):
            self.gets += 1
            if self.gets > 4:
                raise AssertionError("deferred command was read again while paused")
            if self._items:
                return self._items.pop(0)
            raise queue.Empty

        def put(self, item):
            self.requeued.append(item)
            self._items.append(item)

    harness = tmp_path / "harness"
    harness.mkdir()
    cq = RequeueingQueue()
    blocked = BlockState()
    assert check_signals(cq, harness, None, blocked) is True
    assert cq.requeued == [{"cmd": "approve"}]


# --- check_gate tests ---


def test_check_gate_file_missing(tmp_path):
    passed, reason = check_gate(tmp_path / "nonexistent.md", "test_phase")
    assert not passed
    assert "not found" in reason


def test_check_gate_blocked(tmp_path):
    gate_file = tmp_path / "gate.md"
    gate_file.write_text("line1\nline2\nline3\n**STATUS: BLOCKED**\n", encoding="utf-8")
    passed, reason = check_gate(gate_file, "test_phase")
    assert not passed
    assert "BLOCKED" in reason


def test_check_gate_passes(tmp_path):
    gate_file = tmp_path / "gate.md"
    gate_file.write_text("line1\nline2\nline3\nline4\n**STATUS: DONE**\n", encoding="utf-8")
    passed, reason = check_gate(gate_file, "test_phase")
    assert passed
    assert reason == ""


def test_check_gate_blocked_not_in_tail(tmp_path):
    gate_file = tmp_path / "gate.md"
    lines = ["line1"] * 1 + ["**STATUS: BLOCKED**"] + ["lineN"] * 7 + ["**STATUS: DONE**"]
    gate_file.write_text("\n".join(lines), encoding="utf-8")
    passed, _ = check_gate(gate_file, "test_phase")
    assert passed


def test_check_gate_already_done(tmp_path):
    gate_file = tmp_path / "gate.md"
    gate_file.write_text("line1\nline2\nline3\nline4\n**STATUS: ALREADY_DONE**\n", encoding="utf-8")
    passed, _ = check_gate(gate_file, "test_phase")
    assert passed


def test_check_gate_no_status_mark(tmp_path):
    gate_file = tmp_path / "gate.md"
    gate_file.write_text("line1\nline2\nline3\nno status here\n", encoding="utf-8")
    passed, reason = check_gate(gate_file, "test_phase")
    assert not passed
    assert "STATUS: DONE" in reason


def test_check_gate_too_short(tmp_path):
    gate_file = tmp_path / "gate.md"
    gate_file.write_text("short\n**STATUS: DONE**\n", encoding="utf-8")
    passed, reason = check_gate(gate_file, "test_phase")
    assert not passed
    assert "too short" in reason


def test_check_gate_spec_missing_headers(tmp_path):
    gate_file = tmp_path / "spec.md"
    gate_file.write_text("# Spec\nline2\nline3\nline4\n**STATUS: DONE**\n", encoding="utf-8")
    passed, reason = check_gate(gate_file, "spec[1.1]")
    assert not passed
    assert "missing required section" in reason


def test_check_gate_spec_with_headers(tmp_path):
    gate_file = tmp_path / "spec.md"
    content = (
        "# Spec\n"
        "## Objetivo\nDo stuff\n"
        "## Comportamiento Esperado\n- R1: The system shall work.\n"
        "## Criterios de Aceptacion\n- CA1: The system shall pass checks.\n"
        "## Deterministic Check Registry (check_registry)\n"
        "- id: DC1\n"
        "  requirement: CA1\n"
        "  type: command\n"
        "  target: src/tests/test_example.py\n"
        "  command: pytest src/tests/test_example.py\n"
        "  expected: tests pass\n"
        "  evidence_hint: pytest output\n"
        "**STATUS: DONE**\n"
    )
    gate_file.write_text(content, encoding="utf-8")
    passed, _ = check_gate(gate_file, "spec[1.1]")
    assert passed


def test_check_gate_plan_missing_headers(tmp_path):
    gate_file = tmp_path / "plan.md"
    gate_file.write_text("# Plan\nline2\nline3\nline4\n**STATUS: DONE**\n", encoding="utf-8")
    passed, _ = check_gate(gate_file, "plan[2.1]")
    assert not passed


def test_check_gate_plan_with_headers(tmp_path):
    gate_file = tmp_path / "plan.md"
    content = "# Plan\n## Changes\nEdit X\nStep 2\n**STATUS: DONE**\n"
    gate_file.write_text(content, encoding="utf-8")
    passed, _ = check_gate(gate_file, "plan[2.1]")
    assert passed


def test_check_gate_plan_with_spanish_headers(tmp_path):
    gate_file = tmp_path / "plan.md"
    content = "# Plan\n## Pasos\n1. Do X\n2. Do Y\n**STATUS: DONE**\n"
    gate_file.write_text(content, encoding="utf-8")
    passed, _ = check_gate(gate_file, "plan[2.1]")
    assert passed


def test_check_gate_spec_with_english_headers(tmp_path):
    gate_file = tmp_path / "spec.md"
    content = (
        "# Spec\n"
        "## Objective\nDo stuff\n"
        "## Expected Behavior\n- R1: The system shall work.\n"
        "## Acceptance Criteria\n- CA1: The system shall pass checks.\n"
        "## Deterministic Check Registry (check_registry)\n"
        "- id: DC1\n"
        "  requirement: CA1\n"
        "  type: command\n"
        "  target: src/tests/test_example.py\n"
        "  command: pytest src/tests/test_example.py\n"
        "  expected: tests pass\n"
        "  evidence_hint: pytest output\n"
        "**STATUS: DONE**\n"
    )
    gate_file.write_text(content, encoding="utf-8")
    passed, _ = check_gate(gate_file, "spec[1.1]")
    assert passed


def test_check_gate_unknown_phase_no_headers_required(tmp_path):
    gate_file = tmp_path / "brainstorm.md"
    gate_file.write_text("line1\nline2\nline3\nline4\n**STATUS: DONE**\n", encoding="utf-8")
    passed, _ = check_gate(gate_file, "research")
    assert passed


# --- parse_plan_steps tests ---


def test_parse_plan_steps_multiple():
    plan = (
        "# Plan\n\n"
        "## Changes\n\n"
        "### 1. Create file\nDo something\n\n"
        "### 2. Modify file\nChange something\n\n"
        "### 3. Add tests\nTest something\n\n"
        "## Verification\n\nRun tests\n"
    )
    steps = parse_plan_steps(plan)
    assert len(steps) == 3
    assert steps[0].startswith("### 1.")
    assert steps[1].startswith("### 2.")
    assert steps[2].startswith("### 3.")
    assert "Do something" in steps[0]
    assert "Change something" in steps[1]
    assert "Test something" in steps[2]


def test_parse_plan_steps_no_section():
    plan = "# Plan\n\n## Summary\nSome text\n\n## Verification\nRun tests\n"
    assert parse_plan_steps(plan) == []


def test_parse_plan_steps_no_numbered_steps():
    plan = "# Plan\n\n## Changes\n\nJust some prose without numbered steps.\n\n## Verification\n"
    assert parse_plan_steps(plan) == []


def test_parse_plan_steps_single_step():
    plan = "# Plan\n\n## Changes\n\n### 1. Only step\nDo the thing\n\n## Verification\n"
    steps = parse_plan_steps(plan)
    assert len(steps) == 1
    assert steps[0].startswith("### 1.")
    assert "Do the thing" in steps[0]


def test_parse_plan_steps_alternative_heading():
    plan = "# Plan\n\n## Pasos\n\n### 1. Crear archivo\nHacer algo\n\n### 2. Modificar\nCambiar algo\n"
    steps = parse_plan_steps(plan)
    assert len(steps) == 2
    assert steps[0].startswith("### 1.")
    assert steps[1].startswith("### 2.")


def test_parse_plan_steps_intro_text_discarded():
    plan = (
        "# Plan\n\n"
        "## Changes\n\n"
        "Here is some introductory text before the steps.\n\n"
        "### 1. First step\nDo first thing\n"
    )
    steps = parse_plan_steps(plan)
    assert len(steps) == 1
    assert steps[0].startswith("### 1.")
    assert "introductory" not in steps[0]


# --- 2.4 fixtures ---


@pytest.fixture
def hitl_harness(tmp_path):
    """Create a minimal harness dir for HITL tests."""
    h = tmp_path / "harness"
    h.mkdir()
    (h / "_gate_mode").write_text("auto", encoding="utf-8")
    tasks = [
        {"id": "1", "title": "Task 1", "status": "pending"},
        {"id": "2", "title": "Task 2", "status": "pending"},
        {"id": "3", "title": "Task 3", "status": "pending"},
    ]
    (h / "tasks.json").write_text(json.dumps(tasks, indent=2), encoding="utf-8")
    (h / "audit.md").write_text("APPROVED\n", encoding="utf-8")
    return h


@pytest.fixture
def mock_notify(monkeypatch):
    """Mock notify and update_state for HITL tests."""
    notify_calls = []
    def fake_notify(msg):
        notify_calls.append(msg)
    monkeypatch.setattr(mission_runner_mod, "notify", fake_notify)
    monkeypatch.setattr(hitl_mod, "notify", fake_notify)
    monkeypatch.setattr(mission_runner_mod, "update_state", lambda *a, **kw: None)
    monkeypatch.setattr(hitl_mod, "update_state", lambda *a, **kw: None)
    return {"notify_calls": notify_calls}


@pytest.fixture
def mock_compact_imports(monkeypatch):
    """Mock imports used by _consolidate_tasks and compact logic."""
    mock_render = MagicMock(return_value="COMPACT_PROMPT")
    mock_callback = MagicMock(return_value=lambda *a, **kw: None)
    fake_tools = [
        {"name": "Read", "type": "fake"},
        {"name": "Write", "type": "fake"},
        {"name": "Bash", "type": "fake"},
    ]
    mock_agent_run = MagicMock()

    monkeypatch.setattr(reporting_mod, "render_prompt", mock_render)
    monkeypatch.setattr(reporting_mod, "make_tool_callback", mock_callback)
    monkeypatch.setattr(reporting_mod, "TOOL_DEFINITIONS", fake_tools)
    monkeypatch.setattr(_al, "run_phase", mock_agent_run)

    return {
        "render_prompt": mock_render,
        "make_tool_callback": mock_callback,
        "tools": fake_tools,
        "agent_run": mock_agent_run,
    }


@pytest.fixture
def mock_deferred_imports(monkeypatch):
    """Mock imports used by PhaseRunner."""
    mock_result = PhaseResult(text="PHASE_RESULT", turns=5, elapsed=10.0,
                              input_tokens=1000, output_tokens=500)
    mock_render = MagicMock(return_value="RENDERED_PROMPT")
    mock_load_agent = MagicMock(return_value="SYSTEM_PROMPT")
    mock_callback = MagicMock(return_value=lambda *a, **kw: None)
    mock_write_metric = MagicMock()
    fake_tools = [
        {"name": "Read", "type": "fake"},
        {"name": "Write", "type": "fake"},
        {"name": "Bash", "type": "fake"},
    ]
    mock_agent_run = MagicMock(return_value=mock_result)

    monkeypatch.setattr(phase_runner_mod, "render_prompt", mock_render)
    monkeypatch.setattr(phase_runner_mod, "load_agent_system", mock_load_agent)
    monkeypatch.setattr(phase_runner_mod, "make_tool_callback", mock_callback)
    monkeypatch.setattr(phase_runner_mod, "_write_metric", mock_write_metric)
    monkeypatch.setattr(phase_runner_mod, "TOOL_DEFINITIONS", fake_tools)
    monkeypatch.setattr(_al, "run_phase", mock_agent_run)

    return {
        "render_prompt": mock_render,
        "load_agent_system": mock_load_agent,
        "make_tool_callback": mock_callback,
        "write_metric": mock_write_metric,
        "tools": fake_tools,
        "agent_run": mock_agent_run,
    }


# --- 2.4: _parse_status_files tests ---


def test_parse_status_files_happy(tmp_path):
    h = tmp_path / "harness"
    h.mkdir()
    (h / "status.md").write_text(
        "# Status\nDone.\n## Files\n- src/foo.py\n- `src/bar.py`\n  -  src/baz.py  \n## Validation\nPASS\n",
        encoding="utf-8",
    )
    result = _parse_status_files(h)
    assert result == ["src/foo.py", "src/bar.py", "src/baz.py"]


def test_parse_status_files_no_file(tmp_path):
    h = tmp_path / "harness"
    h.mkdir()
    assert _parse_status_files(h) == []


def test_parse_status_files_empty_section(tmp_path):
    h = tmp_path / "harness"
    h.mkdir()
    (h / "status.md").write_text("## Files\n## Next Section\n", encoding="utf-8")
    assert _parse_status_files(h) == []


# --- 2.4: _update_task tests ---


def test_update_task_changes_status(tmp_path):
    h = tmp_path / "harness"
    h.mkdir()
    tasks = [
        {"id": "1", "status": "pending"},
        {"id": "2", "status": "pending"},
    ]
    (h / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")
    _update_task(1, "completed", h)
    updated = json.loads((h / "tasks.json").read_text(encoding="utf-8"))
    assert updated[1]["status"] == "completed"
    assert updated[0]["status"] == "pending"


# --- 2.4: _task_summary tests ---


def test_task_summary_happy(tmp_path):
    h = tmp_path / "harness"
    h.mkdir()
    tasks = [
        {"id": "1", "status": "completed"},
        {"id": "2", "status": "failed"},
        {"id": "3", "status": "pending"},
        {"id": "4", "status": "pending"},
    ]
    (h / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")
    result = _task_summary(h)
    assert "Total: 4" in result
    assert "Completed: 1" in result
    assert "Failed: 1" in result
    assert "Pending: 2" in result


def test_task_summary_missing_file(tmp_path):
    h = tmp_path / "harness"
    h.mkdir()
    assert _task_summary(h) == "No tasks.json found"


# --- 3.1: _is_mission_abort tests ---


def test_is_mission_abort():
    assert _is_mission_abort("user_abort") is True
    assert _is_mission_abort("signal_SIGTERM") is True
    assert _is_mission_abort("signal_SIGINT") is True
    assert _is_mission_abort("") is False
    assert _is_mission_abort("implement (timeout)") is False
    assert _is_mission_abort("spec (gate_fail)") is False
    assert _is_mission_abort("review[1.1] (USER_REJECTED)") is False
    assert _is_mission_abort("compact[1.1] (timeout)") is False
    assert _is_mission_abort("reimplement_fail") is False


# --- 2.4: _audit_verdict tests ---


def test_audit_verdict_approved(tmp_path):
    h = tmp_path / "harness"
    h.mkdir()
    (h / "audit.md").write_text("Review result: APPROVED\n", encoding="utf-8")
    assert _audit_verdict(h) == "APPROVED"


def test_audit_verdict_changes_requested(tmp_path):
    h = tmp_path / "harness"
    h.mkdir()
    (h / "audit.md").write_text("CHANGES_REQUESTED\nPlease fix.\n", encoding="utf-8")
    assert _audit_verdict(h) == "CHANGES_REQUESTED"


def test_audit_verdict_unknown(tmp_path):
    h = tmp_path / "harness"
    h.mkdir()
    assert _audit_verdict(h) == "UNKNOWN"


# --- 2.4: stage_task_files tests ---


def test_stage_task_files_with_files(tmp_path, monkeypatch):
    import src.harness.tasks as tasks_mod
    h = tmp_path / "harness"
    h.mkdir()
    (h / "status.md").write_text("## Files\n- src/a.py\n- src/b.py\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("a", encoding="utf-8")
    (tmp_path / "src" / "b.py").write_text("b", encoding="utf-8")

    calls = []
    monkeypatch.setattr(tasks_mod, "subprocess", type("M", (), {
        "run": staticmethod(lambda cmd, **kw: calls.append(cmd))
    })())
    monkeypatch.chdir(tmp_path)

    stage_task_files(h)
    assert len(calls) == 2
    assert calls[0] == ["git", "add", "src/a.py"]
    assert calls[1] == ["git", "add", "src/b.py"]


def test_stage_task_files_no_files(tmp_path, monkeypatch):
    h = tmp_path / "harness"
    h.mkdir()
    printed = []
    monkeypatch.setattr("builtins.print", lambda *a, **kw: printed.append(str(a)))
    stage_task_files(h)
    assert any("WARNING" in s for s in printed)


# --- 2.4: final_commit tests ---


def test_final_commit_with_changes(tmp_path, monkeypatch):
    import src.core.git as git_mod
    calls = []
    def fake_run(cmd, **kw):
        calls.append(cmd)
        m = MagicMock()
        m.returncode = 1 if "diff" in cmd else 0
        return m
    monkeypatch.setattr(git_mod, "subprocess", type("M", (), {
        "run": staticmethod(fake_run)
    })())

    final_commit("do stuff", "Total: 1 | Completed: 1")
    assert len(calls) == 2
    assert "diff" in calls[0]
    assert "commit" in calls[1]


def test_final_commit_nothing_staged(tmp_path, monkeypatch):
    import src.core.git as git_mod
    def fake_run(cmd, **kw):
        m = MagicMock()
        m.returncode = 0
        return m
    monkeypatch.setattr(git_mod, "subprocess", type("M", (), {
        "run": staticmethod(fake_run)
    })())

    printed = []
    monkeypatch.setattr("builtins.print", lambda *a, **kw: printed.append(str(a)))
    final_commit("do stuff", "Total: 0")
    assert any("nothing to commit" in s.lower() for s in printed)


# --- _consolidate_tasks tests ---


def test_consolidate_tasks_happy_path(tmp_path, mock_compact_imports, reset_blocked):
    h = tmp_path / "harness"
    h.mkdir()
    original = [{"id": str(i), "title": f"Task {i}", "files": [], "complexity": "low", "status": "pending"}
                for i in range(1, 11)]
    (h / "tasks.json").write_text(json.dumps(original), encoding="utf-8")

    consolidated = [{"id": str(i), "title": f"Merged {i}", "files": [], "complexity": "medium", "status": "pending"}
                    for i in range(1, 6)]

    def fake_run_phase(*a, **kw):
        (h / "tasks.json").write_text(json.dumps(consolidated), encoding="utf-8")

    mock_compact_imports["agent_run"].side_effect = fake_run_phase

    _consolidate_tasks(MagicMock(), harness=h, harness_win=str(h),
                       project_dir=str(tmp_path), max_tasks=8)

    assert not (h / "_tasks_backup.json").exists()
    assert mock_compact_imports["agent_run"].call_count == 1
    result = json.loads((h / "tasks.json").read_text(encoding="utf-8"))
    assert len(result) == 5


def test_consolidate_tasks_invalid_json_restores_backup(tmp_path, mock_compact_imports, reset_blocked):
    h = tmp_path / "harness"
    h.mkdir()
    original = [{"id": str(i), "title": f"Task {i}", "files": [], "complexity": "low", "status": "pending"}
                for i in range(1, 11)]
    (h / "tasks.json").write_text(json.dumps(original), encoding="utf-8")

    def fake_run_phase(*a, **kw):
        (h / "tasks.json").write_text("NOT VALID JSON {{{", encoding="utf-8")

    mock_compact_imports["agent_run"].side_effect = fake_run_phase

    _consolidate_tasks(MagicMock(), harness=h, harness_win=str(h),
                       project_dir=str(tmp_path), max_tasks=8)

    result = json.loads((h / "tasks.json").read_text(encoding="utf-8"))
    assert len(result) == 10
    assert not (h / "_tasks_backup.json").exists()


def test_consolidate_tasks_exception_restores_backup(tmp_path, mock_compact_imports, reset_blocked):
    h = tmp_path / "harness"
    h.mkdir()
    original = [{"id": str(i), "title": f"Task {i}", "files": [], "complexity": "low", "status": "pending"}
                for i in range(1, 11)]
    (h / "tasks.json").write_text(json.dumps(original), encoding="utf-8")

    mock_compact_imports["agent_run"].side_effect = PhaseTimeout("timeout")

    _consolidate_tasks(MagicMock(), harness=h, harness_win=str(h),
                       project_dir=str(tmp_path), max_tasks=8)

    result = json.loads((h / "tasks.json").read_text(encoding="utf-8"))
    assert len(result) == 10
    assert not (h / "_tasks_backup.json").exists()


def test_consolidate_tasks_still_over_limit(tmp_path, mock_compact_imports, reset_blocked):
    h = tmp_path / "harness"
    h.mkdir()
    original = [{"id": str(i), "title": f"Task {i}", "files": [], "complexity": "low", "status": "pending"}
                for i in range(1, 11)]
    (h / "tasks.json").write_text(json.dumps(original), encoding="utf-8")

    still_too_many = [{"id": str(i), "title": f"Task {i}", "files": [], "complexity": "low", "status": "pending"}
                      for i in range(1, 10)]

    def fake_run_phase(*a, **kw):
        (h / "tasks.json").write_text(json.dumps(still_too_many), encoding="utf-8")

    mock_compact_imports["agent_run"].side_effect = fake_run_phase

    _consolidate_tasks(MagicMock(), harness=h, harness_win=str(h),
                       project_dir=str(tmp_path), max_tasks=8)

    result = json.loads((h / "tasks.json").read_text(encoding="utf-8"))
    assert len(result) == 9
    assert not (h / "_tasks_backup.json").exists()


def test_consolidate_tasks_missing_schema_restores_backup(tmp_path, mock_compact_imports, reset_blocked):
    h = tmp_path / "harness"
    h.mkdir()
    original = [{"id": str(i), "title": f"Task {i}", "files": [], "complexity": "low", "status": "pending"}
                for i in range(1, 11)]
    (h / "tasks.json").write_text(json.dumps(original), encoding="utf-8")

    bad_schema = [{"name": "foo"}]

    def fake_run_phase(*a, **kw):
        (h / "tasks.json").write_text(json.dumps(bad_schema), encoding="utf-8")

    mock_compact_imports["agent_run"].side_effect = fake_run_phase

    _consolidate_tasks(MagicMock(), harness=h, harness_win=str(h),
                       project_dir=str(tmp_path), max_tasks=8)

    result = json.loads((h / "tasks.json").read_text(encoding="utf-8"))
    assert len(result) == 10
    assert not (h / "_tasks_backup.json").exists()


def test_generate_report_logs_and_injects_token_cost_summary(tmp_path, monkeypatch):
    h = tmp_path / "harness"
    h.mkdir()
    (h / "tasks.json").write_text(
        json.dumps([{"id": "1", "title": "Task", "status": "completed"}]),
        encoding="utf-8",
    )
    write_phase_event(h, "spec[1]", result="success", input_tokens=100, output_tokens=25)

    captured = {}

    def fake_render(template, variables, includes, harness_win):
        captured["template"] = template
        captured["variables"] = variables
        return "REPORT_PROMPT"

    def fake_run_phase(*args, **kwargs):
        captured["user_prompt"] = kwargs["user_prompt"]
        return PhaseResult(text="done", turns=1, elapsed=0.1, input_tokens=0, output_tokens=0)

    monkeypatch.setenv("CLAUDE_HARNESS_TOKEN_BUDGET", "200")
    monkeypatch.setattr(reporting_mod, "render_prompt", fake_render)
    monkeypatch.setattr(_al, "run_phase", fake_run_phase)

    logs = []
    reporting_mod.generate_report(
        MagicMock(),
        task="task",
        branch="branch",
        mode="spec-plan",
        harness=h,
        harness_win=str(h),
        project_dir=tmp_path,
        blocked=BlockState(),
        log=logs.append,
    )

    summary = captured["variables"]["TOKEN_COST_SUMMARY"]
    assert summary in logs
    assert "total_tokens=125" in summary
    assert "token_budget=200" in summary
    assert "budget_status=within_budget" in summary
    assert captured["user_prompt"] == "REPORT_PROMPT"


# --- 2.4: notify tests ---


def test_notify_with_telegram(monkeypatch, reset_blocked):
    import src.integrations.notifier as notifier_mod
    import src.core.notification as notification_mod
    monkeypatch.setattr(notification_mod, "_notify_backend", notifier_mod.notify)
    monkeypatch.setenv("TELEGRAM_TOKEN", "tok123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat456")

    import src.integrations.telegram_api as _api
    send_calls = []
    monkeypatch.setattr(_api, "send_message", lambda t, c, m: send_calls.append((t, c, m)))

    notify("hello world")
    assert len(send_calls) == 1
    assert send_calls[0][0] == "tok123"
    assert send_calls[0][1] == "chat456"
    assert "hello world" in send_calls[0][2]


def test_notify_without_telegram(monkeypatch, reset_blocked):
    import src.integrations.notifier as notifier_mod
    import src.core.notification as notification_mod
    monkeypatch.setattr(notification_mod, "_notify_backend", notifier_mod.notify)
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    import src.integrations.telegram_api as _api
    send_calls = []
    monkeypatch.setattr(_api, "send_message", lambda t, c, m: send_calls.append(1))

    notify("hello")
    assert len(send_calls) == 0


def test_notify_truncation(monkeypatch, reset_blocked):
    import src.integrations.notifier as notifier_mod
    import src.core.notification as notification_mod
    monkeypatch.setattr(notification_mod, "_notify_backend", notifier_mod.notify)
    monkeypatch.setenv("TELEGRAM_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")

    import src.integrations.telegram_api as _api
    captured = []
    monkeypatch.setattr(_api, "send_message", lambda t, c, m: captured.append(m))

    long_msg = "x" * 5000
    notify(long_msg)
    assert len(captured) == 1
    assert len(captured[0]) <= 4000


# --- 2.4: notify_result tests ---


def test_notify_result_blocked(tmp_path, reset_blocked, monkeypatch):
    from src.integrations.notifier import notify_result as _real_nr
    monkeypatch.setattr(reporting_mod, "_notify_result_backend", _real_nr)

    h = tmp_path / "harness"
    h.mkdir()
    (h / "mission-report.md").write_text("Report line 1\nReport line 2\n", encoding="utf-8")
    blocked = BlockState()
    blocked.reason = BlockReason(BlockKind.TIMEOUT, phase="some_phase")

    notify_calls = []
    monkeypatch.setattr(reporting_mod, "notify", lambda msg: notify_calls.append(msg))

    notify_result("my task", "feat-x", h, blocked)
    assert len(notify_calls) == 1
    assert "\U0001f6ab" in notify_calls[0]
    assert "BLOCKED" in notify_calls[0]
    assert "some_phase" in notify_calls[0]


def test_notify_result_complete(tmp_path, reset_blocked, monkeypatch):
    from src.integrations.notifier import notify_result as _real_nr
    monkeypatch.setattr(reporting_mod, "_notify_result_backend", _real_nr)

    h = tmp_path / "harness"
    h.mkdir()
    (h / "mission-report.md").write_text("Report line 1\n", encoding="utf-8")
    blocked = BlockState()

    notify_calls = []
    monkeypatch.setattr(reporting_mod, "notify", lambda msg: notify_calls.append(msg))

    notify_result("my task", "feat-x", h, blocked)
    assert len(notify_calls) == 1
    assert "✅" in notify_calls[0]
    assert "COMPLETE" in notify_calls[0]



# --- 2.5: main flow integration tests ---


def _mock_orchestration(monkeypatch, harness):
    """Mock orchestration functions so main() runs without side effects past setup."""
    harness.mkdir(exist_ok=True)
    (harness / "_gate_mode").write_text("auto", encoding="utf-8")
    monkeypatch.setattr(mission, "_load_env", lambda: None)
    monkeypatch.setattr("src.core.git.ensure_develop", lambda: "existing")
    monkeypatch.setattr("src.core.git.setup_git", lambda b: "existing")
    monkeypatch.setattr(mission, "_create_client", lambda: MagicMock())
    monkeypatch.setattr("src.harness.registry.register_mission", lambda t, h, p: None)
    monkeypatch.setattr(mission_runner_mod, "notify", lambda msg: None)
    monkeypatch.setattr(hitl_mod, "notify", lambda msg: None)
    monkeypatch.setattr(PhaseRunner, "run", lambda *a, **kw: None)
    monkeypatch.setattr(PhaseRunner, "run_conversation", lambda *a, **kw: None)
    monkeypatch.setattr(BurstRunner, "compact_context", lambda *a, **kw: None)
    monkeypatch.setattr(HitlReviewer, "commit_task", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "build_code_graph", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "generate_report", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "notify_result", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "final_commit", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "merge_to_develop", lambda *a, **kw: True)
    monkeypatch.setattr(mission_runner_mod, "update_state", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "_update_task", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "_task_summary", lambda *a, **kw: "")
    monkeypatch.setattr(mission_runner_mod, "stage_task_files", lambda *a, **kw: None)
    monkeypatch.setattr("src.mission.human_input._start_stdin_listener", lambda q: None)
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)


def test_main_sets_proc_state(tmp_path, monkeypatch, reset_blocked, save_env):
    """main() sets MissionProcess notify_prefix and mission_tag from harness_info."""
    harness = tmp_path / "harness"
    fake_info = {
        "harness": harness,
        "harness_win": str(harness),
        "mission_tag": "test-proj_feat-x_12345",
        "project_name": "test-proj",
        "branch_safe": "feat-x",
    }
    ns = argparse.Namespace(
        task="do stuff", branch="feat-x", mode="full",
        no_grill=False, resume=False, gate=False, task_file=None,
        max_tasks=8,
    )
    monkeypatch.setattr(mission, "parse_args", lambda: ns)
    monkeypatch.setattr(mission, "resolve_args", lambda a: None)
    monkeypatch.setattr("src.harness.harness_utils.setup_harness", lambda b, g, **kw: fake_info)
    _mock_orchestration(monkeypatch, harness)

    class FakeAtexit:
        register = staticmethod(lambda fn: None)
    monkeypatch.setattr(mission, "atexit", FakeAtexit)

    class FakeSignal:
        SIGTERM = 15
        SIGINT = 2
        signal = staticmethod(lambda s, h: None)
    monkeypatch.setattr(mission, "signal", FakeSignal)

    printed = []
    monkeypatch.setattr("builtins.print", lambda *a, **kw: printed.append(a))

    proc = mission.main()

    expected_prefix = compute_notify_prefix("test-proj")
    assert proc.notify_prefix == expected_prefix
    assert proc.mission_tag == "test-proj_feat-x_12345"


def test_main_registers_atexit(tmp_path, monkeypatch, reset_blocked, save_env):
    """main() calls atexit.register(proc.cleanup)."""
    harness = tmp_path / "harness"
    fake_info = {
        "harness": harness,
        "harness_win": str(harness),
        "mission_tag": "tag",
        "project_name": "proj",
        "branch_safe": "br",
    }
    ns = argparse.Namespace(
        task="t", branch="b", mode="full",
        no_grill=False, resume=False, gate=False, task_file=None,
        max_tasks=8,
    )
    monkeypatch.setattr(mission, "parse_args", lambda: ns)
    monkeypatch.setattr(mission, "resolve_args", lambda a: None)
    monkeypatch.setattr("src.harness.harness_utils.setup_harness", lambda b, g, **kw: fake_info)
    _mock_orchestration(monkeypatch, harness)

    atexit_calls = []
    class FakeAtexit:
        @staticmethod
        def register(fn):
            atexit_calls.append(fn)
    monkeypatch.setattr(mission, "atexit", FakeAtexit)

    class FakeSignal:
        SIGTERM = 15
        SIGINT = 2
        signal = staticmethod(lambda s, h: None)
    monkeypatch.setattr(mission, "signal", FakeSignal)

    printed = []
    monkeypatch.setattr("builtins.print", lambda *a, **kw: printed.append(a))

    proc = mission.main()

    assert len(atexit_calls) == 1
    assert atexit_calls[0] == proc.cleanup


def test_main_registers_signals(tmp_path, monkeypatch, reset_blocked, save_env):
    """main() registers SIGTERM and SIGINT handlers."""
    import signal as real_signal
    harness = tmp_path / "harness"
    fake_info = {
        "harness": harness,
        "harness_win": str(harness),
        "mission_tag": "tag",
        "project_name": "proj",
        "branch_safe": "br",
    }
    ns = argparse.Namespace(
        task="t", branch="b", mode="full",
        no_grill=False, resume=False, gate=False, task_file=None,
        max_tasks=8,
    )
    monkeypatch.setattr(mission, "parse_args", lambda: ns)
    monkeypatch.setattr(mission, "resolve_args", lambda a: None)
    monkeypatch.setattr("src.harness.harness_utils.setup_harness", lambda b, g, **kw: fake_info)
    _mock_orchestration(monkeypatch, harness)

    class FakeAtexit:
        register = staticmethod(lambda fn: None)
    monkeypatch.setattr(mission, "atexit", FakeAtexit)

    signal_calls = []
    class FakeSignal:
        SIGTERM = real_signal.SIGTERM
        SIGINT = real_signal.SIGINT
        @staticmethod
        def signal(sig, handler):
            signal_calls.append((sig, handler))
    monkeypatch.setattr(mission, "signal", FakeSignal)

    printed = []
    monkeypatch.setattr("builtins.print", lambda *a, **kw: printed.append(a))

    proc = mission.main()

    assert len(signal_calls) == 2
    sigs = {s for s, h in signal_calls}
    assert real_signal.SIGTERM in sigs
    assert real_signal.SIGINT in sigs
    for _, handler in signal_calls:
        assert handler == proc.signal_handler


# --- 2.2: consolidation integration tests ---


def test_main_consolidates_when_over_limit(tmp_path, monkeypatch, reset_blocked, save_env):
    """main() calls _consolidate_tasks when tasks exceed max_tasks."""
    harness = tmp_path / "harness"
    fake_info = {
        "harness": harness,
        "harness_win": str(harness),
        "mission_tag": "tag",
        "project_name": "proj",
        "branch_safe": "br",
    }
    ns = argparse.Namespace(
        task="t", branch="b", mode="full",
        no_grill=False, resume=False, gate=False, task_file=None,
        max_tasks=3,
    )
    monkeypatch.setattr(mission, "parse_args", lambda: ns)
    monkeypatch.setattr(mission, "resolve_args", lambda a: None)
    monkeypatch.setattr("src.harness.harness_utils.setup_harness", lambda b, g, **kw: fake_info)
    _mock_orchestration(monkeypatch, harness)

    tasks = [{"id": str(i), "title": f"Task {i}", "status": "pending"}
             for i in range(1, 6)]
    (harness / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")

    consolidate_calls = []
    def fake_consolidate(*a, **kw):
        consolidate_calls.append(kw)
        merged = [{"id": str(i), "title": f"Task {i}", "status": "pending"}
                  for i in range(1, 4)]
        (harness / "tasks.json").write_text(json.dumps(merged), encoding="utf-8")

    monkeypatch.setattr(mission_runner_mod, "_consolidate_tasks", fake_consolidate)

    class FakeAtexit:
        register = staticmethod(lambda fn: None)
    monkeypatch.setattr(mission, "atexit", FakeAtexit)
    monkeypatch.setattr(mission, "signal", MagicMock())
    monkeypatch.setattr("builtins.print", lambda *a, **kw: None)

    mission.main()

    assert len(consolidate_calls) == 1
    assert consolidate_calls[0]["max_tasks"] == 3


def test_main_skips_consolidation_on_resume(tmp_path, monkeypatch, reset_blocked, save_env):
    """main() skips _consolidate_tasks when resuming, even with excess tasks."""
    harness = tmp_path / "harness"
    fake_info = {
        "harness": harness,
        "harness_win": str(harness),
        "mission_tag": "tag",
        "project_name": "proj",
        "branch_safe": "br",
    }
    ns = argparse.Namespace(
        task="t", branch="b", mode="full",
        no_grill=False, resume=True, gate=False, task_file=None,
        max_tasks=3,
    )
    monkeypatch.setattr(mission, "parse_args", lambda: ns)
    monkeypatch.setattr(mission, "resolve_args", lambda a: None)
    monkeypatch.setattr("src.harness.harness_utils.setup_harness", lambda b, g, **kw: fake_info)
    _mock_orchestration(monkeypatch, harness)

    tasks = [{"id": str(i), "title": f"Task {i}", "status": "pending"}
             for i in range(1, 6)]
    (harness / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")

    consolidate_calls = []
    def fake_consolidate(*a, **kw):
        consolidate_calls.append(kw)

    monkeypatch.setattr(mission_runner_mod, "_consolidate_tasks", fake_consolidate)

    class FakeAtexit:
        register = staticmethod(lambda fn: None)
    monkeypatch.setattr(mission, "atexit", FakeAtexit)
    monkeypatch.setattr(mission, "signal", MagicMock())
    monkeypatch.setattr("builtins.print", lambda *a, **kw: None)

    mission.main()

    assert len(consolidate_calls) == 0


def test_main_no_consolidation_under_limit(tmp_path, monkeypatch, reset_blocked, save_env):
    """main() does not call _consolidate_tasks when tasks <= max_tasks."""
    harness = tmp_path / "harness"
    fake_info = {
        "harness": harness,
        "harness_win": str(harness),
        "mission_tag": "tag",
        "project_name": "proj",
        "branch_safe": "br",
    }
    ns = argparse.Namespace(
        task="t", branch="b", mode="full",
        no_grill=False, resume=False, gate=False, task_file=None,
        max_tasks=8,
    )
    monkeypatch.setattr(mission, "parse_args", lambda: ns)
    monkeypatch.setattr(mission, "resolve_args", lambda a: None)
    monkeypatch.setattr("src.harness.harness_utils.setup_harness", lambda b, g, **kw: fake_info)
    _mock_orchestration(monkeypatch, harness)

    tasks = [{"id": "1", "title": "Task 1", "status": "pending"}]
    (harness / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")

    consolidate_calls = []
    def fake_consolidate(*a, **kw):
        consolidate_calls.append(kw)

    monkeypatch.setattr(mission_runner_mod, "_consolidate_tasks", fake_consolidate)

    class FakeAtexit:
        register = staticmethod(lambda fn: None)
    monkeypatch.setattr(mission, "atexit", FakeAtexit)
    monkeypatch.setattr(mission, "signal", MagicMock())
    monkeypatch.setattr("builtins.print", lambda *a, **kw: None)

    mission.main()

    assert len(consolidate_calls) == 0


# --- 2.5: cleanup tests ---


def test_cleanup_happy(monkeypatch):
    """cleanup() unregisters mission and sets cleanup_done."""
    proc = mission.MissionProcess()
    proc.mission_tag = "test-tag"

    unreg_calls = []
    monkeypatch.setattr("src.harness.registry.unregister_mission", lambda t: unreg_calls.append(t))
    monkeypatch.setattr("src.harness.registry.list_missions", lambda: [])

    printed = []
    monkeypatch.setattr("builtins.print", lambda *a, **kw: printed.append(a))

    proc.cleanup()

    assert len(unreg_calls) == 1
    assert unreg_calls[0] == "test-tag"
    assert proc.cleanup_done is True


def test_cleanup_idempotent(monkeypatch):
    """Calling cleanup() twice only unregisters once."""
    proc = mission.MissionProcess()
    proc.mission_tag = "test-tag"

    unreg_calls = []
    monkeypatch.setattr("src.harness.registry.unregister_mission", lambda t: unreg_calls.append(t))
    monkeypatch.setattr("src.harness.registry.list_missions", lambda: [])

    printed = []
    monkeypatch.setattr("builtins.print", lambda *a, **kw: printed.append(a))

    proc.cleanup()
    proc.cleanup()

    assert len(unreg_calls) == 1


def test_cleanup_empty_tag(monkeypatch):
    """cleanup() no-ops when mission_tag is empty."""
    proc = mission.MissionProcess()

    unreg_calls = []
    monkeypatch.setattr("src.harness.registry.unregister_mission", lambda t: unreg_calls.append(t))
    monkeypatch.setattr("src.harness.registry.list_missions", lambda: [])

    proc.cleanup()

    assert len(unreg_calls) == 0
    assert proc.cleanup_done is False


def test_cleanup_already_done(monkeypatch):
    """cleanup() no-ops when cleanup_done is True."""
    proc = mission.MissionProcess()
    proc.mission_tag = "tag"
    proc.cleanup_done = True

    unreg_calls = []
    monkeypatch.setattr("src.harness.registry.unregister_mission", lambda t: unreg_calls.append(t))
    monkeypatch.setattr("src.harness.registry.list_missions", lambda: [])

    proc.cleanup()

    assert len(unreg_calls) == 0


# --- 2.5: signal_handler tests ---


def test_signal_handler_sigterm(monkeypatch, reset_blocked):
    """signal_handler(SIGTERM) sets blocked, calls cleanup, exits."""
    import signal as real_signal
    proc = mission.MissionProcess()
    proc.mission_tag = "tag"
    blocked = BlockState()
    proc.blocked = blocked

    unreg_calls = []
    monkeypatch.setattr("src.harness.registry.unregister_mission", lambda t: unreg_calls.append(t))
    monkeypatch.setattr("src.harness.registry.list_missions", lambda: [])

    printed = []
    monkeypatch.setattr("builtins.print", lambda *a, **kw: printed.append(a))

    with pytest.raises(SystemExit) as exc:
        proc.signal_handler(real_signal.SIGTERM, None)

    assert exc.value.code == 1
    assert blocked.value == "signal_SIGTERM"
    assert proc.cleanup_done is True
    assert len(unreg_calls) == 1


def test_signal_handler_sigint(monkeypatch, reset_blocked):
    """signal_handler(SIGINT) sets blocked to signal_SIGINT."""
    import signal as real_signal
    proc = mission.MissionProcess()
    proc.mission_tag = "tag"
    blocked = BlockState()
    proc.blocked = blocked

    unreg_calls = []
    monkeypatch.setattr("src.harness.registry.unregister_mission", lambda t: unreg_calls.append(t))
    monkeypatch.setattr("src.harness.registry.list_missions", lambda: [])

    printed = []
    monkeypatch.setattr("builtins.print", lambda *a, **kw: printed.append(a))

    with pytest.raises(SystemExit) as exc:
        proc.signal_handler(real_signal.SIGINT, None)

    assert exc.value.code == 1
    assert blocked.value == "signal_SIGINT"
    assert proc.cleanup_done is True


# --- ensure_develop tests ---


def test_ensure_develop_creates(monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        m = MagicMock()
        if cmd[:4] == ["git", "show-ref", "--verify", "--quiet"]:
            m.returncode = 1
        else:
            m.returncode = 0
            m.stdout = "refs/remotes/origin/master\n"
        return m

    monkeypatch.setattr("src.core.git.subprocess.run", fake_run)
    monkeypatch.setattr("src.core.git.detect_base_branch", lambda: "master")
    result = ensure_develop()
    assert result == "created"
    assert any("develop" in str(c) for c in calls)


def test_ensure_develop_existing(monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        m = MagicMock()
        m.returncode = 0
        return m

    monkeypatch.setattr("src.core.git.subprocess.run", fake_run)
    result = ensure_develop()
    assert result == "existing"
    assert ["git", "checkout", "develop"] in calls


# --- merge_to_develop tests ---


def _write_validation_script(tmp_path):
    script = tmp_path / "mission-validate.cmd"
    script.write_text("@echo off\nexit /b 0\n", encoding="utf-8")
    return script


def test_merge_to_develop_success(tmp_path, monkeypatch):
    _write_validation_script(tmp_path)
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        m = MagicMock()
        m.returncode = 0
        m.stdout = "all passed"
        m.stderr = ""
        return m

    monkeypatch.setattr("src.core.git.subprocess.run", fake_run)
    log_msgs = []
    result = merge_to_develop("feature/test", lambda msg: log_msgs.append(msg), project_dir=tmp_path)
    assert result is True
    assert any("Merged" in m for m in log_msgs)


def test_merge_to_develop_test_fail(tmp_path, monkeypatch):
    validation = _write_validation_script(tmp_path)

    def fake_run(cmd, **kw):
        m = MagicMock()
        if str(validation) in cmd:
            m.returncode = 1
            m.stdout = "FAILED test_foo"
            m.stderr = ""
        else:
            m.returncode = 0
        return m

    monkeypatch.setattr("src.core.git.subprocess.run", fake_run)
    log_msgs = []
    result = merge_to_develop("feature/test", lambda msg: log_msgs.append(msg), project_dir=tmp_path)
    assert result is False
    assert any("FAILED" in m for m in log_msgs)


def test_merge_to_develop_conflict(tmp_path, monkeypatch):
    validation = _write_validation_script(tmp_path)
    call_count = [0]
    calls = []

    def fake_run(cmd, **kw):
        call_count[0] += 1
        calls.append(cmd)
        m = MagicMock()
        m.stdout = ""
        m.stderr = ""
        if str(validation) in cmd:
            m.returncode = 0
            m.stdout = "all passed"
        elif cmd[:2] == ["git", "merge"]:
            if "--abort" not in cmd:
                m.returncode = 1
                m.stderr = "CONFLICT"
            else:
                m.returncode = 0
        else:
            m.returncode = 0
        return m

    monkeypatch.setattr("src.core.git.subprocess.run", fake_run)
    log_msgs = []
    result = merge_to_develop("feature/test", lambda msg: log_msgs.append(msg), project_dir=tmp_path)
    assert result is False
    assert any("FAILED" in m or "Merge" in m for m in log_msgs)
    assert ["git", "merge", "--abort"] in calls
    assert ["git", "checkout", "feature/test"] in calls


# --- auto branch name tests ---


def test_auto_branch_name_from_task():
    ns = parse_args(["modernize code graph"])
    ns.task_file = None
    assert ns.branch is None
    resolve_args(ns)
    assert ns.branch.startswith("feature/")
    assert "modernize" in ns.branch


# --- build_code_graph tests ---


def test_build_code_graph_success(monkeypatch):
    logs = []
    fake_result = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="Built graph: 42 nodes, 10 edges", stderr=""
    )
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: fake_result)
    build_code_graph("/project", log=lambda m: logs.append(m))
    assert len(logs) == 1
    assert "42 nodes" in logs[0]


def test_build_code_graph_failure(monkeypatch):
    logs = []
    fake_result = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="tree_sitter error"
    )
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: fake_result)
    build_code_graph("/project", log=lambda m: logs.append(m))
    assert len(logs) == 1
    assert "failed" in logs[0]


def test_build_code_graph_timeout(monkeypatch):
    logs = []
    def raise_timeout(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="build", timeout=120)
    monkeypatch.setattr(subprocess, "run", raise_timeout)
    build_code_graph("/project", log=lambda m: logs.append(m))
    assert len(logs) == 1
    assert "timed out" in logs[0]


def test_build_code_graph_exception(monkeypatch):
    logs = []
    def raise_exc(*a, **kw):
        raise OSError("no such file")
    monkeypatch.setattr(subprocess, "run", raise_exc)
    build_code_graph("/project", log=lambda m: logs.append(m))
    assert len(logs) == 1
    assert "error" in logs[0]


def test_build_code_graph_no_log(monkeypatch):
    fake_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr="")
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: fake_result)
    build_code_graph("/project")


def test_build_code_graph_passes_correct_args(monkeypatch):
    captured = []
    def capture_run(*args, **kwargs):
        captured.append(args[0])
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr="")
    monkeypatch.setattr(subprocess, "run", capture_run)
    build_code_graph("/my/project", log=lambda m: None)
    assert len(captured) == 1
    cmd = captured[0]
    assert cmd[0] == sys.executable
    assert "code_graph.py" in cmd[1]
    assert cmd[2] == "build"
    assert cmd[3] == "/my/project"


# --- PhaseRunner tests ---


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


def test_phase_runner_resolve_includes_harness(tmp_path):
    ctx = _make_ctx(tmp_path)
    runner = PhaseRunner(MagicMock(), ctx, BlockState())
    config = PhaseConfig(
        name="test", agent="", template="t.md", gate=None,
        tools=DEFAULT_TOOLS, max_turns=10,
        includes={"SPEC": "spec.md", "PLAN": "plan.md"},
    )
    resolved = runner._resolve_includes(config)
    assert resolved["SPEC"] == str(ctx.harness / "spec.md")
    assert resolved["PLAN"] == str(ctx.harness / "plan.md")


def test_phase_runner_resolve_includes_prompts(tmp_path):
    ctx = _make_ctx(tmp_path)
    runner = PhaseRunner(MagicMock(), ctx, BlockState())
    config = PhaseConfig(
        name="test", agent="", template="t.md", gate=None,
        tools=DEFAULT_TOOLS, max_turns=10,
        includes={"GRAPH_INSTRUCTIONS": "prompts/graph-instructions.md"},
    )
    resolved = runner._resolve_includes(config)
    assert "prompts" in resolved["GRAPH_INSTRUCTIONS"]
    assert "graph-instructions.md" in resolved["GRAPH_INSTRUCTIONS"]
    assert not resolved["GRAPH_INSTRUCTIONS"].startswith(str(ctx.harness))


def test_phase_runner_resolve_includes_extra(tmp_path):
    ctx = _make_ctx(tmp_path)
    runner = PhaseRunner(MagicMock(), ctx, BlockState())
    config = PhaseConfig(
        name="test", agent="", template="t.md", gate=None,
        tools=DEFAULT_TOOLS, max_turns=10,
        includes={"SPEC": "spec.md"},
    )
    resolved = runner._resolve_includes(config, extra_includes={"EXTRA": "/custom/path"})
    assert resolved["SPEC"] == str(ctx.harness / "spec.md")
    assert resolved["EXTRA"] == "/custom/path"


def test_phase_runner_status_artifact_stop_condition(tmp_path):
    ctx = _make_ctx(tmp_path)
    runner = PhaseRunner(MagicMock(), ctx, BlockState())
    config = PhaseConfig(
        name="grill", agent="", template="t.md", gate="brief.md",
        tools=DEFAULT_TOOLS, max_turns=10,
    )
    brief = ctx.harness / "brief.md"
    brief.write_text("STATUS: DONE\nAll good.", encoding="utf-8")
    block = MagicMock(name="write_block")
    block.name = "Write"
    block.input = {"file_path": str(brief)}

    should_stop = runner._status_artifact_stop_condition(config)

    assert should_stop([block]) is True


def test_phase_runner_status_artifact_stop_condition_ignores_other_files(tmp_path):
    ctx = _make_ctx(tmp_path)
    runner = PhaseRunner(MagicMock(), ctx, BlockState())
    config = PhaseConfig(
        name="grill", agent="", template="t.md", gate="brief.md",
        tools=DEFAULT_TOOLS, max_turns=10,
    )
    brief = ctx.harness / "brief.md"
    brief.write_text("STATUS: DONE\nAll good.", encoding="utf-8")
    block = MagicMock(name="write_block")
    block.name = "Write"
    block.input = {"file_path": str(ctx.harness / "other.md")}

    should_stop = runner._status_artifact_stop_condition(config)

    assert should_stop([block]) is False


def test_phase_runner_run_blocked(tmp_path, reset_blocked, mock_deferred_imports):
    blocked = BlockState()
    blocked.reason = BlockReason(BlockKind.TIMEOUT, phase="already")
    ctx = _make_ctx(tmp_path)
    runner = PhaseRunner(MagicMock(), ctx, blocked)
    config = PHASE_REGISTRY["research"]
    result = runner.run(config, variables={"TASK": "t"})
    assert result is None
    mock_deferred_imports["agent_run"].assert_not_called()


def test_phase_runner_run_happy(tmp_path, mock_deferred_imports):
    ctx = _make_ctx(tmp_path)
    gate = ctx.harness / "brainstorm.md"
    gate.write_text("line1\nline2\nall good\nline4\n**STATUS: DONE**\n", encoding="utf-8")
    client = MagicMock()
    runner = PhaseRunner(client, ctx, BlockState())
    config = PHASE_REGISTRY["research"]
    result = runner.run(config, variables={"TASK": "test"})
    assert result == "PHASE_RESULT"
    mock_deferred_imports["agent_run"].assert_called_once()
    assert mock_deferred_imports["agent_run"].call_args[1]["model"] == "claude-sonnet-4-6"


def test_phase_runner_run_timeout(tmp_path, reset_blocked, mock_deferred_imports):
    ctx = _make_ctx(tmp_path)
    mock_deferred_imports["agent_run"].side_effect = PhaseTimeout("timeout", metrics={"turns": 1})
    blocked = BlockState()
    runner = PhaseRunner(MagicMock(), ctx, blocked)
    config = PHASE_REGISTRY["research"]
    result = runner.run(config, variables={"TASK": "t"})
    assert result is None
    assert "timeout" in blocked.value


def test_phase_runner_run_gate_fail(tmp_path, reset_blocked, mock_deferred_imports):
    ctx = _make_ctx(tmp_path)
    gate = ctx.harness / "brainstorm.md"
    gate.write_text("too short\n", encoding="utf-8")
    blocked = BlockState()
    runner = PhaseRunner(MagicMock(), ctx, blocked)
    config = PHASE_REGISTRY["research"]
    result = runner.run(config, variables={"TASK": "t"})
    assert result is None
    assert "gate_fail" in blocked.value


def test_phase_runner_run_no_agent(tmp_path, mock_deferred_imports):
    ctx = _make_ctx(tmp_path)
    runner = PhaseRunner(MagicMock(), ctx, BlockState())
    config = PHASE_REGISTRY["compact"]
    result = runner.run(config, variables={"TASK_ID": "t", "TASK_TITLE": "title"},
                        gate_file_override=None)
    assert result == "PHASE_RESULT"
    mock_deferred_imports["load_agent_system"].assert_not_called()


def test_phase_runner_run_overrides(tmp_path, mock_deferred_imports):
    ctx = _make_ctx(tmp_path)
    runner = PhaseRunner(MagicMock(), ctx, BlockState())
    config = PHASE_REGISTRY["implement"]
    gate = ctx.harness / "status.md"
    gate.write_text(
        "## Routing\n"
        "- task_complexity: M\n"
        "- task_pipeline: spec -> plan -> implement -> review\n"
        "- complexity_reason: normal task needs review\n"
        "## Self-Verification\n"
        "- tests_run: pytest - PASS\n"
        "**STATUS: DONE**\n",
        encoding="utf-8",
    )
    result = runner.run(
        config, variables={"TASK_ID": "t", "TASK_TITLE": "title"},
        phase_name_override="implement[t]#1",
        timeout_override=300,
        max_turns_override=20,
    )
    assert result == "PHASE_RESULT"
    call_kwargs = mock_deferred_imports["agent_run"].call_args[1]
    assert call_kwargs["phase_name"] == "implement[t]#1"
    assert call_kwargs["timeout"] == 300
    assert call_kwargs["max_turns"] == 20


def test_phase_runner_routes_large_task_to_deep_model(tmp_path, mock_deferred_imports):
    ctx = _make_ctx(tmp_path)
    runner = PhaseRunner(MagicMock(), ctx, BlockState())
    config = PHASE_REGISTRY["implement"]
    gate = ctx.harness / "status.md"
    gate.write_text(
        "## Routing\n"
        "- task_complexity: L\n"
        "- task_pipeline: spec -> plan -> implement_bursts -> review\n"
        "- complexity_reason: broad implementation\n"
        "## Self-Verification\n"
        "- tests_run: pytest - PASS\n"
        "**STATUS: DONE**\n",
        encoding="utf-8",
    )

    result = runner.run(
        config,
        variables={"TASK_ID": "t", "TASK_TITLE": "title", "TASK_COMPLEXITY": "L"},
        phase_name_override="implement[t]",
    )

    assert result == "PHASE_RESULT"
    assert mock_deferred_imports["agent_run"].call_args[1]["model"] == "claude-opus-4-7"


# --- MissionRunner tests ---


def test_mission_runner_execute_happy(tmp_path, monkeypatch, reset_blocked, save_env):
    ctx = _make_ctx(tmp_path)
    harness = ctx.harness
    tasks = [{"id": "T1", "title": "Test task", "status": "pending"}]
    (harness / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")

    phase_calls = []
    def spy_run(self_pr, config, variables, **kw):
        phase_calls.append(config.name)

    def spy_conv(self_pr, config, variables, get_input, **kw):
        phase_calls.append(config.name)
    monkeypatch.setattr(PhaseRunner, "run", spy_run)
    monkeypatch.setattr(PhaseRunner, "run_conversation", spy_conv)
    monkeypatch.setattr(BurstRunner, "compact_context", lambda *a, **kw: None)
    monkeypatch.setattr(HitlReviewer, "commit_task", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "build_code_graph", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "generate_report", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "notify_result", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "notify", lambda msg: None)
    monkeypatch.setattr(hitl_mod, "notify", lambda msg: None)
    monkeypatch.setattr(mission_runner_mod, "final_commit", lambda t, s: None)
    monkeypatch.setattr(mission_runner_mod, "merge_to_develop", lambda b, l: True)
    monkeypatch.setattr(mission_runner_mod, "update_state", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "check_signals", lambda *a, **kw: True)
    monkeypatch.setattr("builtins.print", lambda *a, **kw: None)

    ms = MissionState()
    cq = queue.Queue()
    log = lambda msg: None
    runner = create_runner(MagicMock(), ctx, cq, ms, log, BlockState())
    runner.execute()

    assert "research" in phase_calls
    assert "structure" in phase_calls
    assert "grill" in phase_calls
    assert "spec" in phase_calls
    assert "plan" in phase_calls
    assert "review" in phase_calls
    assert (harness / "decisions.md").is_file(), "decisions.md fallback not created"


def test_mission_runner_decisions_fallback(tmp_path, monkeypatch, reset_blocked, save_env):
    """If planner doesn't produce decisions.md, harness creates a fallback."""
    ctx = _make_ctx(tmp_path)
    harness = ctx.harness
    tasks = [{"id": "T1", "title": "Test task", "status": "pending"}]
    (harness / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")

    def spy_run(self_pr, config, variables, **kw):
        pass
    def spy_conv(self_pr, config, variables, get_input, **kw):
        pass
    monkeypatch.setattr(PhaseRunner, "run", spy_run)
    monkeypatch.setattr(PhaseRunner, "run_conversation", spy_conv)
    monkeypatch.setattr(BurstRunner, "compact_context", lambda *a, **kw: None)
    monkeypatch.setattr(HitlReviewer, "commit_task", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "build_code_graph", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "generate_report", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "notify_result", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "notify", lambda msg: None)
    monkeypatch.setattr(hitl_mod, "notify", lambda msg: None)
    monkeypatch.setattr(mission_runner_mod, "final_commit", lambda t, s: None)
    monkeypatch.setattr(mission_runner_mod, "merge_to_develop", lambda b, l: True)
    monkeypatch.setattr(mission_runner_mod, "update_state", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "check_signals", lambda *a, **kw: True)
    monkeypatch.setattr("builtins.print", lambda *a, **kw: None)

    ms = MissionState()
    cq = queue.Queue()
    runner = create_runner(MagicMock(), ctx, cq, ms, lambda m: None, BlockState())
    runner.execute()

    assert (harness / "decisions.md").is_file()
    content = (harness / "decisions.md").read_text(encoding="utf-8")
    assert "No architectural decisions" in content


def test_mission_runner_decisions_not_overwritten(tmp_path, monkeypatch, reset_blocked, save_env):
    """If planner produces decisions.md, harness does not overwrite it."""
    ctx = _make_ctx(tmp_path)
    harness = ctx.harness
    tasks = [{"id": "T1", "title": "Test task", "status": "pending"}]
    (harness / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")

    def spy_run(self_pr, config, variables, **kw):
        if config.name == "plan":
            (harness / "decisions.md").write_text("### ADR-1: Use Redis\n", encoding="utf-8")
    def spy_conv(self_pr, config, variables, get_input, **kw):
        pass
    monkeypatch.setattr(PhaseRunner, "run", spy_run)
    monkeypatch.setattr(PhaseRunner, "run_conversation", spy_conv)
    monkeypatch.setattr(BurstRunner, "compact_context", lambda *a, **kw: None)
    monkeypatch.setattr(HitlReviewer, "commit_task", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "build_code_graph", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "generate_report", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "notify_result", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "notify", lambda msg: None)
    monkeypatch.setattr(hitl_mod, "notify", lambda msg: None)
    monkeypatch.setattr(mission_runner_mod, "final_commit", lambda t, s: None)
    monkeypatch.setattr(mission_runner_mod, "merge_to_develop", lambda b, l: True)
    monkeypatch.setattr(mission_runner_mod, "update_state", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "check_signals", lambda *a, **kw: True)
    monkeypatch.setattr("builtins.print", lambda *a, **kw: None)

    ms = MissionState()
    cq = queue.Queue()
    runner = create_runner(MagicMock(), ctx, cq, ms, lambda m: None, BlockState())
    runner.execute()

    content = (harness / "decisions.md").read_text(encoding="utf-8")
    assert "ADR-1" in content


def test_mission_runner_resume_skips_init(tmp_path, monkeypatch, reset_blocked, save_env):
    ctx = _make_ctx(tmp_path, resume=True)
    harness = ctx.harness
    tasks = [{"id": "T1", "title": "Test task", "status": "completed"}]
    (harness / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")

    phase_calls = []
    def spy_run(self_pr, config, variables, **kw):
        phase_calls.append(config.name)
    monkeypatch.setattr(PhaseRunner, "run", spy_run)
    monkeypatch.setattr(PhaseRunner, "run_conversation", lambda *a, **kw: None)
    monkeypatch.setattr(BurstRunner, "compact_context", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "build_code_graph", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "generate_report", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "notify_result", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "notify", lambda msg: None)
    monkeypatch.setattr(hitl_mod, "notify", lambda msg: None)
    monkeypatch.setattr(mission_runner_mod, "final_commit", lambda t, s: None)
    monkeypatch.setattr(mission_runner_mod, "merge_to_develop", lambda b, l: True)
    monkeypatch.setattr(mission_runner_mod, "update_state", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "check_signals", lambda *a, **kw: True)
    monkeypatch.setattr("builtins.print", lambda *a, **kw: None)

    ms = MissionState()
    cq = queue.Queue()
    runner = create_runner(MagicMock(), ctx, cq, ms, lambda m: None, BlockState())
    runner.execute()

    assert "research" not in phase_calls
    assert "structure" not in phase_calls


def test_mission_runner_blocked_in_init(tmp_path, monkeypatch, reset_blocked, save_env):
    ctx = _make_ctx(tmp_path)
    harness = ctx.harness
    tasks = [{"id": "T1", "title": "t", "status": "pending"}]
    (harness / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")

    def block_research(self_pr, config, variables, **kw):
        if config.name == "research":
            self_pr.blocked.reason = BlockReason(BlockKind.TIMEOUT, phase="research")
    monkeypatch.setattr(PhaseRunner, "run", block_research)
    monkeypatch.setattr(PhaseRunner, "run_conversation", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "generate_report", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "notify_result", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "notify", lambda msg: None)
    monkeypatch.setattr(hitl_mod, "notify", lambda msg: None)
    monkeypatch.setattr(mission_runner_mod, "update_state", lambda *a, **kw: None)
    monkeypatch.setattr("builtins.print", lambda *a, **kw: None)

    ms = MissionState()
    cq = queue.Queue()
    blocked = BlockState()
    runner = create_runner(MagicMock(), ctx, cq, ms, lambda m: None, blocked)
    runner.execute()

    assert blocked.value == "research (timeout)"


def test_mission_runner_no_grill(tmp_path, monkeypatch, reset_blocked, save_env):
    ctx = _make_ctx(tmp_path, no_grill=True)
    harness = ctx.harness
    tasks = [{"id": "T1", "title": "t", "status": "completed"}]
    (harness / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")

    phase_calls = []
    def spy_run(self_pr, config, variables, **kw):
        phase_calls.append(config.name)
    def spy_conv(self_pr, config, variables, get_input, **kw):
        phase_calls.append(config.name)
    monkeypatch.setattr(PhaseRunner, "run", spy_run)
    monkeypatch.setattr(PhaseRunner, "run_conversation", spy_conv)
    monkeypatch.setattr(BurstRunner, "compact_context", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "build_code_graph", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "generate_report", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "notify_result", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "notify", lambda msg: None)
    monkeypatch.setattr(hitl_mod, "notify", lambda msg: None)
    monkeypatch.setattr(mission_runner_mod, "final_commit", lambda t, s: None)
    monkeypatch.setattr(mission_runner_mod, "merge_to_develop", lambda b, l: True)
    monkeypatch.setattr(mission_runner_mod, "update_state", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "check_signals", lambda *a, **kw: True)
    monkeypatch.setattr("builtins.print", lambda *a, **kw: None)

    ms = MissionState()
    cq = queue.Queue()
    runner = create_runner(MagicMock(), ctx, cq, ms, lambda m: None, BlockState())
    runner.execute()

    assert "grill" not in phase_calls
    assert "research" in phase_calls


def _run_mode_test(tmp_path, monkeypatch, reset_blocked, save_env, mode,
                   no_grill=False, extra_patches=None):
    """Helper: run MissionRunner with given mode, return list of phase names called."""
    ctx = _make_ctx(tmp_path, mode=mode, no_grill=no_grill)
    harness = ctx.harness
    tasks = [{"id": "T1", "title": "Test task", "status": "pending"}]
    (harness / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")

    phase_calls = []
    def spy_run(self_pr, config, variables, **kw):
        phase_calls.append(config.name)
    def spy_conv(self_pr, config, variables, get_input, **kw):
        phase_calls.append(config.name)
    monkeypatch.setattr(PhaseRunner, "run", spy_run)
    monkeypatch.setattr(PhaseRunner, "run_conversation", spy_conv)
    monkeypatch.setattr(BurstRunner, "compact_context", lambda *a, **kw: None)
    monkeypatch.setattr(HitlReviewer, "commit_task", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "build_code_graph", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "generate_report", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "notify_result", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "notify", lambda msg: None)
    monkeypatch.setattr(hitl_mod, "notify", lambda msg: None)
    monkeypatch.setattr(mission_runner_mod, "final_commit", lambda t, s: None)
    monkeypatch.setattr(mission_runner_mod, "merge_to_develop", lambda b, l: True)
    monkeypatch.setattr(mission_runner_mod, "update_state", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "check_signals", lambda *a, **kw: True)
    monkeypatch.setattr("builtins.print", lambda *a, **kw: None)
    if extra_patches:
        for obj, attr, value in extra_patches:
            monkeypatch.setattr(obj, attr, value)

    ms = MissionState()
    cq = queue.Queue()
    runner = create_runner(MagicMock(), ctx, cq, ms, lambda m: None, BlockState())
    runner.execute()
    return phase_calls


def test_mode_hotfix_skips_init(tmp_path, monkeypatch, reset_blocked, save_env):
    phases = _run_mode_test(tmp_path, monkeypatch, reset_blocked, save_env, "hotfix")
    assert "research" not in phases
    assert "structure" not in phases
    assert "grill" not in phases
    assert "spec" in phases


def test_mode_focused_no_compact_no_grill(tmp_path, monkeypatch, reset_blocked, save_env):
    phases = _run_mode_test(tmp_path, monkeypatch, reset_blocked, save_env, "focused")
    assert "research" in phases
    assert "structure" in phases
    assert "grill" not in phases


def test_mode_explore_only_research(tmp_path, monkeypatch, reset_blocked, save_env):
    """Explore mode runs only research (brainstorm), no structure, no task loop."""
    phases = _run_mode_test(tmp_path, monkeypatch, reset_blocked, save_env, "explore")
    assert "research" in phases
    assert "structure" not in phases
    assert "grill" not in phases
    assert "spec" not in phases
    assert "implement" not in phases


def test_mode_spec_has_grill(tmp_path, monkeypatch, reset_blocked, save_env):
    phases = _run_mode_test(tmp_path, monkeypatch, reset_blocked, save_env, "spec")
    assert "research" in phases
    assert "grill" in phases
    assert "structure" in phases


def test_mode_spec_plan_has_grill(tmp_path, monkeypatch, reset_blocked, save_env):
    phases = _run_mode_test(tmp_path, monkeypatch, reset_blocked, save_env, "spec-plan")
    assert "research" in phases
    assert "grill" in phases
    assert "structure" in phases


def test_mode_full_has_grill(tmp_path, monkeypatch, reset_blocked, save_env):
    phases = _run_mode_test(tmp_path, monkeypatch, reset_blocked, save_env, "full")
    assert "research" in phases
    assert "grill" in phases
    assert "structure" in phases


def test_finalize_spec_plan_no_merge(tmp_path, monkeypatch, reset_blocked, save_env):
    """Spec-plan mode has no 'merge' in finalize — merge_to_develop should not be called."""
    merge_calls = []
    spy = lambda b, l: merge_calls.append(b) or True
    _run_mode_test(tmp_path, monkeypatch, reset_blocked, save_env, "spec-plan",
                   extra_patches=[(mission_runner_mod, "merge_to_develop", spy)])
    assert len(merge_calls) == 0


def test_finalize_partial_modes_no_merge(tmp_path, monkeypatch, reset_blocked, save_env):
    for mode in ("spec", "spec-plan"):
        merge_calls = []
        spy = lambda b, l: merge_calls.append(b) or True
        _run_mode_test(tmp_path, monkeypatch, reset_blocked, save_env, mode,
                       extra_patches=[(mission_runner_mod, "merge_to_develop", spy)])
        assert merge_calls == []


def test_finalize_full_merges(tmp_path, monkeypatch, reset_blocked, save_env):
    """Full mode has 'merge' in finalize — merge_to_develop should be called."""
    merge_calls = []
    spy = lambda b, l: merge_calls.append(b) or True
    _run_mode_test(tmp_path, monkeypatch, reset_blocked, save_env, "full",
                   extra_patches=[(mission_runner_mod, "merge_to_develop", spy)])
    assert len(merge_calls) == 1


def test_finalize_focused_merges(tmp_path, monkeypatch, reset_blocked, save_env):
    """Focused mode declares merge in finalize pipeline."""
    merge_calls = []
    spy = lambda b, l: merge_calls.append(b) or True
    _run_mode_test(tmp_path, monkeypatch, reset_blocked, save_env, "focused",
                   extra_patches=[(mission_runner_mod, "merge_to_develop", spy)])
    assert len(merge_calls) == 1


# --- Task pipeline tests (complexity S/M/L) ---

def _run_task_pipeline_test(tmp_path, monkeypatch, reset_blocked, save_env,
                            complexity="M", mode="full"):
    """Helper: run MissionRunner with a task of given complexity, return phase names."""
    ctx = _make_ctx(tmp_path, mode=mode)
    harness = ctx.harness
    tasks = [{"id": "T1", "title": "Test task", "complexity": complexity,
              "status": "pending"}]
    (harness / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")

    phase_calls = []
    def spy_run(self_pr, config, variables, **kw):
        phase_calls.append(config.name)
    def spy_conv(self_pr, config, variables, get_input, **kw):
        phase_calls.append(config.name)
    monkeypatch.setattr(PhaseRunner, "run", spy_run)
    monkeypatch.setattr(PhaseRunner, "run_conversation", spy_conv)
    monkeypatch.setattr(BurstRunner, "compact_context", lambda *a, **kw: None)
    monkeypatch.setattr(HitlReviewer, "commit_task", lambda *a, **kw: None)
    monkeypatch.setattr(BurstRunner, "run_implement_bursts", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "build_code_graph", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "generate_report", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "notify_result", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "notify", lambda msg: None)
    monkeypatch.setattr(hitl_mod, "notify", lambda msg: None)
    monkeypatch.setattr(mission_runner_mod, "final_commit", lambda t, s: None)
    monkeypatch.setattr(mission_runner_mod, "merge_to_develop", lambda b, l: True)
    monkeypatch.setattr(mission_runner_mod, "update_state", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "check_signals", lambda *a, **kw: True)
    monkeypatch.setattr(mission_runner_mod, "stage_task_files", lambda h: None)
    monkeypatch.setattr("builtins.print", lambda *a, **kw: None)

    ms = MissionState()
    cq = queue.Queue()
    runner = create_runner(MagicMock(), ctx, cq, ms, lambda m: None, BlockState())
    runner.execute()
    return phase_calls


def test_task_pipeline_s_only_implement(tmp_path, monkeypatch, reset_blocked, save_env):
    """S-complexity tasks run only implement, skip spec/plan/review."""
    phases = _run_task_pipeline_test(tmp_path, monkeypatch, reset_blocked, save_env, "S")
    task_phases = [p for p in phases if p in ("spec", "plan", "implement", "review")]
    assert task_phases == ["implement"]


def test_task_pipeline_m_full_cycle(tmp_path, monkeypatch, reset_blocked, save_env):
    """M-complexity tasks run spec → plan → implement → review."""
    phases = _run_task_pipeline_test(tmp_path, monkeypatch, reset_blocked, save_env, "M")
    task_phases = [p for p in phases if p in ("spec", "plan", "implement", "review")]
    assert task_phases == ["spec", "plan", "implement", "review"]


def test_task_pipeline_l_uses_bursts(tmp_path, monkeypatch, reset_blocked, save_env):
    """L-complexity tasks call _run_implement_bursts instead of monolithic implement."""
    ctx = _make_ctx(tmp_path, mode="full")
    harness = ctx.harness
    tasks = [{"id": "T1", "title": "Test task", "complexity": "L",
              "status": "pending"}]
    (harness / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")

    phase_calls = []
    burst_called = []
    def spy_run(self_pr, config, variables, **kw):
        phase_calls.append(config.name)
    def spy_conv(self_pr, config, variables, get_input, **kw):
        phase_calls.append(config.name)
    def spy_bursts(self_mr, tid, ttitle, task_vars=None):
        burst_called.append((tid, task_vars))
    monkeypatch.setattr(PhaseRunner, "run", spy_run)
    monkeypatch.setattr(PhaseRunner, "run_conversation", spy_conv)
    monkeypatch.setattr(BurstRunner, "compact_context", lambda *a, **kw: None)
    monkeypatch.setattr(HitlReviewer, "commit_task", lambda *a, **kw: None)
    monkeypatch.setattr(BurstRunner, "run_implement_bursts", spy_bursts)
    monkeypatch.setattr(mission_runner_mod, "build_code_graph", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "generate_report", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "notify_result", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "notify", lambda msg: None)
    monkeypatch.setattr(hitl_mod, "notify", lambda msg: None)
    monkeypatch.setattr(mission_runner_mod, "final_commit", lambda t, s: None)
    monkeypatch.setattr(mission_runner_mod, "merge_to_develop", lambda b, l: True)
    monkeypatch.setattr(mission_runner_mod, "update_state", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "check_signals", lambda *a, **kw: True)
    monkeypatch.setattr("builtins.print", lambda *a, **kw: None)

    ms = MissionState()
    cq = queue.Queue()
    runner = create_runner(MagicMock(), ctx, cq, ms, lambda m: None, BlockState())
    runner.execute()

    assert burst_called[0][0] == "T1"
    assert burst_called[0][1]["TASK_COMPLEXITY"] == "L"
    assert "implement" not in phase_calls


def test_task_pipeline_s_auto_approves(tmp_path, monkeypatch, reset_blocked, save_env):
    """S tasks without review get auto-approved (stage + complete, no _commit_task)."""
    ctx = _make_ctx(tmp_path, mode="full")
    harness = ctx.harness
    tasks = [{"id": "T1", "title": "Simple fix", "complexity": "S",
              "status": "pending"}]
    (harness / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")

    staged = []
    commit_called = []
    def spy_run(self_pr, config, variables, **kw):
        pass
    def spy_conv(self_pr, config, variables, get_input, **kw):
        pass
    def spy_commit(self_mr, *a, **kw):
        commit_called.append(True)
    def spy_stage(h):
        staged.append(True)
    monkeypatch.setattr(PhaseRunner, "run", spy_run)
    monkeypatch.setattr(PhaseRunner, "run_conversation", spy_conv)
    monkeypatch.setattr(BurstRunner, "compact_context", lambda *a, **kw: None)
    monkeypatch.setattr(HitlReviewer, "commit_task", spy_commit)
    monkeypatch.setattr(mission_runner_mod, "build_code_graph", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "generate_report", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "notify_result", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "notify", lambda msg: None)
    monkeypatch.setattr(hitl_mod, "notify", lambda msg: None)
    monkeypatch.setattr(mission_runner_mod, "final_commit", lambda t, s: None)
    monkeypatch.setattr(mission_runner_mod, "merge_to_develop", lambda b, l: True)
    monkeypatch.setattr(mission_runner_mod, "update_state", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "check_signals", lambda *a, **kw: True)
    monkeypatch.setattr(mission_runner_mod, "stage_task_files", spy_stage)
    monkeypatch.setattr("builtins.print", lambda *a, **kw: None)

    ms = MissionState()
    cq = queue.Queue()
    runner = create_runner(MagicMock(), ctx, cq, ms, lambda m: None, BlockState())
    runner.execute()

    assert staged == [True], "S tasks should stage files without review"
    assert commit_called == [], "S tasks should NOT call _commit_task"


def test_task_pipeline_logs_and_passes_complexity_reason(tmp_path, monkeypatch, reset_blocked, save_env):
    ctx = _make_ctx(tmp_path, mode="full")
    harness = ctx.harness
    tasks = [{
        "id": "T1",
        "title": "Simple fix",
        "complexity": "S",
        "complexity_reason": "single file and low regression risk",
        "status": "pending",
    }]
    (harness / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")

    logs = []
    phase_variables = []

    def spy_run(self_pr, config, variables, **kw):
        phase_variables.append(variables)

    monkeypatch.setattr(PhaseRunner, "run", spy_run)
    monkeypatch.setattr(PhaseRunner, "run_conversation", lambda *a, **kw: None)
    monkeypatch.setattr(BurstRunner, "compact_context", lambda *a, **kw: None)
    monkeypatch.setattr(HitlReviewer, "commit_task", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "build_code_graph", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "generate_report", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "notify_result", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "notify", lambda msg: None)
    monkeypatch.setattr(hitl_mod, "notify", lambda msg: None)
    monkeypatch.setattr(mission_runner_mod, "final_commit", lambda t, s: None)
    monkeypatch.setattr(mission_runner_mod, "merge_to_develop", lambda b, l: True)
    monkeypatch.setattr(mission_runner_mod, "update_state", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "check_signals", lambda *a, **kw: True)
    monkeypatch.setattr(mission_runner_mod, "stage_task_files", lambda h: None)
    monkeypatch.setattr("builtins.print", lambda *a, **kw: None)

    ms = MissionState()
    cq = queue.Queue()
    runner = create_runner(MagicMock(), ctx, cq, ms, logs.append, BlockState())
    runner.execute()

    assert any("complexity_reason=single file and low regression risk" in m for m in logs)
    task_variables = next(v for v in phase_variables if v.get("TASK_ID") == "T1")
    assert task_variables["TASK_COMPLEXITY"] == "S"
    assert task_variables["TASK_PIPELINE"] == "implement"
    assert task_variables["TASK_COMPLEXITY_REASON"] == "single file and low regression risk"
    events = read_events(harness)
    assert [e["event_type"] for e in events] == ["task_started", "task_completed"]
    assert events[0]["complexity_reason"] == "single file and low regression risk"


def test_task_pipeline_spec_plan_mode_overrides_low_complexity(tmp_path, monkeypatch, reset_blocked, save_env):
    """Spec-plan mode forces spec → plan pipeline regardless of S complexity."""
    phases = _run_task_pipeline_test(tmp_path, monkeypatch, reset_blocked, save_env,
                                    "S", mode="spec-plan")
    task_phases = [p for p in phases if p in ("spec", "plan", "implement", "review")]
    assert task_phases == ["spec", "plan"]


def test_task_pipeline_spec_mode_overrides_complexity(tmp_path, monkeypatch, reset_blocked, save_env):
    phases = _run_task_pipeline_test(tmp_path, monkeypatch, reset_blocked, save_env,
                                    "L", mode="spec")
    task_phases = [p for p in phases if p in ("spec", "plan", "implement", "review")]
    assert task_phases == ["spec"]


def test_task_pipeline_spec_plan_mode_overrides_complexity(tmp_path, monkeypatch, reset_blocked, save_env):
    phases = _run_task_pipeline_test(tmp_path, monkeypatch, reset_blocked, save_env,
                                    "S", mode="spec-plan")
    task_phases = [p for p in phases if p in ("spec", "plan", "implement", "review")]
    assert task_phases == ["spec", "plan"]


def test_partial_task_pipeline_completes_without_staging(tmp_path, monkeypatch, reset_blocked, save_env):
    ctx = _make_ctx(tmp_path, mode="spec")
    harness = ctx.harness
    tasks = [{"id": "T1", "title": "Spec only", "complexity": "S", "status": "pending"}]
    (harness / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")

    staged = []
    committed = []
    phase_variables = []

    def spy_run(self_pr, config, variables, **kw):
        phase_variables.append(variables)

    monkeypatch.setattr(PhaseRunner, "run", spy_run)
    monkeypatch.setattr(PhaseRunner, "run_conversation", lambda *a, **kw: None)
    monkeypatch.setattr(BurstRunner, "compact_context", lambda *a, **kw: None)
    monkeypatch.setattr(HitlReviewer, "commit_task", lambda *a, **kw: committed.append(True))
    monkeypatch.setattr(mission_runner_mod, "build_code_graph", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "generate_report", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "notify_result", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "notify", lambda msg: None)
    monkeypatch.setattr(hitl_mod, "notify", lambda msg: None)
    monkeypatch.setattr(mission_runner_mod, "final_commit", lambda t, s: None)
    monkeypatch.setattr(mission_runner_mod, "merge_to_develop", lambda b, l: True)
    monkeypatch.setattr(mission_runner_mod, "update_state", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "check_signals", lambda *a, **kw: True)
    monkeypatch.setattr(mission_runner_mod, "stage_task_files", lambda h: staged.append(True))
    monkeypatch.setattr("builtins.print", lambda *a, **kw: None)

    ms = MissionState()
    cq = queue.Queue()
    runner = create_runner(MagicMock(), ctx, cq, ms, lambda m: None, BlockState())
    runner.execute()

    updated_tasks = json.loads((harness / "tasks.json").read_text(encoding="utf-8"))
    task_variables = next(v for v in phase_variables if v.get("TASK_ID") == "T1")
    assert task_variables["TASK_PIPELINE"] == "spec"
    assert updated_tasks[0]["status"] == "completed"
    assert staged == []
    assert committed == []


def test_task_pipeline_defaults_to_m(tmp_path, monkeypatch, reset_blocked, save_env):
    """Tasks without complexity field default to M pipeline."""
    ctx = _make_ctx(tmp_path, mode="full")
    harness = ctx.harness
    tasks = [{"id": "T1", "title": "No complexity", "status": "pending"}]
    (harness / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")

    phase_calls = []
    def spy_run(self_pr, config, variables, **kw):
        phase_calls.append(config.name)
    def spy_conv(self_pr, config, variables, get_input, **kw):
        phase_calls.append(config.name)
    monkeypatch.setattr(PhaseRunner, "run", spy_run)
    monkeypatch.setattr(PhaseRunner, "run_conversation", spy_conv)
    monkeypatch.setattr(BurstRunner, "compact_context", lambda *a, **kw: None)
    monkeypatch.setattr(HitlReviewer, "commit_task", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "build_code_graph", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "generate_report", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "notify_result", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "notify", lambda msg: None)
    monkeypatch.setattr(hitl_mod, "notify", lambda msg: None)
    monkeypatch.setattr(mission_runner_mod, "final_commit", lambda t, s: None)
    monkeypatch.setattr(mission_runner_mod, "merge_to_develop", lambda b, l: True)
    monkeypatch.setattr(mission_runner_mod, "update_state", lambda *a, **kw: None)
    monkeypatch.setattr(mission_runner_mod, "check_signals", lambda *a, **kw: True)
    monkeypatch.setattr("builtins.print", lambda *a, **kw: None)

    ms = MissionState()
    cq = queue.Queue()
    runner = create_runner(MagicMock(), ctx, cq, ms, lambda m: None, BlockState())
    runner.execute()

    task_phases = [p for p in phase_calls if p in ("spec", "plan", "implement", "review")]
    assert task_phases == ["spec", "plan", "implement", "review"]


# --- structural: dependency direction ---


def test_core_does_not_import_integrations():
    core_dir = Path(__file__).resolve().parent.parent / "core"
    violations = []
    for py_file in sorted(core_dir.glob("*.py")):
        for i, line in enumerate(py_file.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "from src.integrations" in stripped or "import src.integrations" in stripped:
                violations.append(f"{py_file.name}:{i}: {stripped}")
    assert violations == [], f"core imports integrations: {violations}"
