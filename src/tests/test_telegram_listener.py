import sys
import json
import queue
from pathlib import Path

from src.harness import harness_utils
from src.harness import registry as _registry

from src.integrations import telegram_listener
from src.integrations import telegram_api
from src.integrations import telegram_commands
from src.integrations.telegram_listener import (
    MissionState, HELP_TEXT, ARTIFACT_COMMANDS, COMMANDS,
)
from src.integrations.telegram_api import _msg_ctx
from src.integrations.constants import PROJECT_COLORS
import pytest


@pytest.fixture
def mock_send(monkeypatch):
    sent = []
    monkeypatch.setattr(telegram_api, "send_message",
                        lambda t, c, msg, **kw: sent.append(msg))
    return sent


@pytest.fixture
def harness(tmp_path, monkeypatch):
    monkeypatch.setattr(telegram_listener, "resolve_harness",
                        lambda tag: (tmp_path, tag))
    monkeypatch.setattr(_registry, "REGISTRY_PATH",
                        tmp_path / "_missions.json")
    return tmp_path


# Area 1: handle_command dispatch


class TestHandleCommandDispatch:

    def test_help(self, mock_send, harness):
        telegram_listener.handle_command("tok", "1", "/help", harness)
        assert HELP_TEXT in mock_send[0]

    def test_start(self, mock_send, harness):
        telegram_listener.handle_command("tok", "1", "/start", harness)
        assert HELP_TEXT in mock_send[0]

    def test_artifact_brief(self, mock_send, harness):
        (harness / "brief.md").write_text("mission brief content")
        telegram_listener.handle_command("tok", "1", "/brief", harness)
        assert "mission brief content" in mock_send[0]

    def test_unknown_command(self, mock_send, harness):
        telegram_listener.handle_command("tok", "1", "/xyzzy", harness)
        assert "Unknown command" in mock_send[0]
        assert HELP_TEXT in mock_send[0]

    def test_non_command_ignored(self, mock_send, harness):
        telegram_listener.handle_command("tok", "1", "hello world", harness)
        assert len(mock_send) == 0


# Area 2: command handlers queue mode


class TestCmdHandlersQueueMode:

    def test_cmd_status_mission_state(self, mock_send):
        ms = MissionState(
            phase="implement", task_id="1.1", task_title="Fix bug",
            task_num=2, task_count=5, completed=1,
            mode="full", gate="manual",
        )
        telegram_commands.cmd_status("tok", "1", [], Path("/tmp"), mission_state=ms)
        msg = mock_send[0]
        assert "Task 2/5" in msg
        assert "1.1" in msg
        assert "Fix bug" in msg
        assert "manual" in msg

    def test_cmd_abort_queue(self, mock_send):
        q = queue.Queue()
        telegram_commands.cmd_abort("tok", "1", [], Path("/tmp"), command_queue=q)
        assert q.get_nowait() == {"cmd": "abort"}
        assert any("Abort" in m or "abort" in m.lower() for m in mock_send)

    def test_cmd_pause_queue(self, mock_send):
        q = queue.Queue()
        telegram_commands.cmd_pause("tok", "1", [], Path("/tmp"), command_queue=q)
        assert q.get_nowait() == {"cmd": "pause"}

    def test_cmd_resume_queue(self, mock_send):
        q = queue.Queue()
        telegram_commands.cmd_resume("tok", "1", [], Path("/tmp"), command_queue=q)
        assert q.get_nowait() == {"cmd": "resume"}

    def test_cmd_approve_queue(self, mock_send):
        q = queue.Queue()
        telegram_commands.cmd_approve("tok", "1", [], Path("/tmp"), command_queue=q)
        assert q.get_nowait() == {"cmd": "approve"}

    def test_cmd_skip_queue(self, mock_send):
        q = queue.Queue()
        telegram_commands.cmd_skip("tok", "1", [], Path("/tmp"), command_queue=q)
        assert q.get_nowait() == {"cmd": "skip"}

    def test_cmd_gate_on_queue(self, mock_send):
        q = queue.Queue()
        telegram_commands.cmd_gate("tok", "1", ["on"], Path("/tmp"), command_queue=q)
        assert q.get_nowait() == {"cmd": "gate", "mode": "manual"}

    def test_cmd_gate_off_queue(self, mock_send):
        q = queue.Queue()
        telegram_commands.cmd_gate("tok", "1", ["off"], Path("/tmp"), command_queue=q)
        assert q.get_nowait() == {"cmd": "gate", "mode": "auto"}

    def test_cmd_reject_queue_with_reason(self, mock_send):
        q = queue.Queue()
        telegram_commands.cmd_reject("tok", "1", ["bad", "code"], Path("/tmp"), command_queue=q)
        assert q.get_nowait() == {"cmd": "reject", "reason": "bad code"}

    def test_cmd_retry_queue_with_feedback(self, mock_send):
        q = queue.Queue()
        telegram_commands.cmd_retry("tok", "1", ["fix", "tests"], Path("/tmp"), command_queue=q)
        assert q.get_nowait() == {"cmd": "retry", "feedback": "fix tests"}


# Area 3: command handlers file mode


class TestCmdHandlersFileMode:

    def test_cmd_log_found(self, mock_send, tmp_path):
        lines = [f"line {i}" for i in range(40)]
        (tmp_path / "mission.log").write_text(chr(10).join(lines))
        telegram_commands.cmd_log("tok", "1", [], tmp_path)
        msg = mock_send[0]
        assert "line 39" in msg
        assert "line 10" in msg
        assert "line 9" not in msg

    def test_cmd_log_not_found(self, mock_send, tmp_path):
        telegram_commands.cmd_log("tok", "1", [], tmp_path)
        assert "No mission log" in mock_send[0]

    def test_cmd_verbose_default(self, mock_send, tmp_path):
        lines = [f"  > tool call {i}" for i in range(25)]
        lines += ["normal line"] * 5
        (tmp_path / "mission.log").write_text(chr(10).join(lines))
        telegram_commands.cmd_verbose("tok", "1", [], tmp_path)
        msg = mock_send[0]
        assert "tool call 24" in msg
        assert "tool call 5" in msg
        assert "tool call 4" not in msg

    def test_cmd_verbose_with_n(self, mock_send, tmp_path):
        lines = [f"  > tool {i}" for i in range(30)]
        (tmp_path / "mission.log").write_text(chr(10).join(lines))
        telegram_commands.cmd_verbose("tok", "1", ["5"], tmp_path)
        msg = mock_send[0]
        assert "tool 29" in msg
        assert "tool 25" in msg
        assert "tool 24" not in msg

    def test_cmd_verbose_clamped_to_50(self, mock_send, tmp_path):
        lines = [f"  > tool {i}" for i in range(60)]
        (tmp_path / "mission.log").write_text(chr(10).join(lines))
        telegram_commands.cmd_verbose("tok", "1", ["999"], tmp_path)
        msg = mock_send[0]
        assert "tool 59" in msg
        assert "tool 10" in msg
        assert "tool 9" not in msg

    def test_cmd_verbose_no_tool_lines(self, mock_send, tmp_path):
        (tmp_path / "mission.log").write_text("normal line 1" + chr(10) + "normal line 2" + chr(10))
        telegram_commands.cmd_verbose("tok", "1", [], tmp_path)
        assert "No activity yet." in mock_send[0]

    def test_cmd_verbose_no_tool_lines_with_progress(self, mock_send, tmp_path):
        (tmp_path / "mission.log").write_text("normal line" + chr(10))
        (tmp_path / "_progress.txt").write_text("implementing step 3")
        telegram_commands.cmd_verbose("tok", "1", [], tmp_path)
        assert "implementing step 3" in mock_send[0]

    def test_cmd_status_no_state_file(self, mock_send, tmp_path):
        telegram_commands.cmd_status("tok", "1", [], tmp_path)
        assert "No active mission state." in mock_send[0]

    def test_cmd_gate_invalid_arg(self, mock_send, tmp_path):
        telegram_commands.cmd_gate("tok", "1", ["maybe"], tmp_path)
        assert "Usage:" in mock_send[0]

    def test_cmd_gate_empty_args(self, mock_send, tmp_path):
        telegram_commands.cmd_gate("tok", "1", [], tmp_path)
        assert "Usage:" in mock_send[0]

    def test_cmd_abort_file_mode(self, mock_send, tmp_path):
        telegram_commands.cmd_abort("tok", "1", [], tmp_path)
        assert (tmp_path / "_cmd_abort").exists()

    def test_cmd_pause_file_mode(self, mock_send, tmp_path):
        telegram_commands.cmd_pause("tok", "1", [], tmp_path)
        assert (tmp_path / "_cmd_pause").exists()

    def test_cmd_approve_file_mode(self, mock_send, tmp_path):
        telegram_commands.cmd_approve("tok", "1", [], tmp_path)
        assert (tmp_path / "_cmd_approve").exists()

    def test_cmd_skip_file_mode(self, mock_send, tmp_path):
        telegram_commands.cmd_skip("tok", "1", [], tmp_path)
        assert (tmp_path / "_cmd_skip").exists()

    def test_cmd_resume_file_mode_unlinks_pause(self, mock_send, tmp_path):
        (tmp_path / "_cmd_pause").write_text("")
        telegram_commands.cmd_resume("tok", "1", [], tmp_path)
        assert not (tmp_path / "_cmd_pause").exists()
        assert "resumed" in mock_send[0].lower()

    def test_cmd_reject_file_no_reason(self, mock_send, tmp_path):
        telegram_commands.cmd_reject("tok", "1", [], tmp_path)
        assert (tmp_path / "_cmd_reject").exists()
        assert (tmp_path / "_cmd_reject").read_text() == ""

    def test_cmd_reject_file_with_reason(self, mock_send, tmp_path):
        telegram_commands.cmd_reject("tok", "1", ["needs", "work"], tmp_path)
        assert (tmp_path / "_cmd_reject").read_text() == "needs work"

    def test_cmd_retry_file_with_feedback(self, mock_send, tmp_path):
        telegram_commands.cmd_retry("tok", "1", ["fix", "it"], tmp_path)
        assert (tmp_path / "_cmd_retry").read_text() == "fix it"

    def test_cmd_gate_on_file_mode(self, mock_send, tmp_path):
        telegram_commands.cmd_gate("tok", "1", ["on"], tmp_path)
        assert (tmp_path / "_gate_mode").read_text() == "manual"

    def test_cmd_gate_off_file_mode(self, mock_send, tmp_path):
        telegram_commands.cmd_gate("tok", "1", ["off"], tmp_path)
        assert (tmp_path / "_gate_mode").read_text() == "auto"


# Area 4: check_waiting_approval with MissionState


class TestCheckWaitingMissionState:

    def test_waiting_none(self, mock_send):
        ms = MissionState(waiting_approval=None)
        telegram_listener.check_waiting_approval("tok", "1", mission_state=ms)
        assert len(mock_send) == 0

    def test_already_notified(self, mock_send):
        ms = MissionState(
            waiting_approval={"verdict": "APPROVED", "task_id": "1.1", "task_title": "T"},
            waiting_notified=True,
        )
        telegram_listener.check_waiting_approval("tok", "1", mission_state=ms)
        assert len(mock_send) == 0

    def test_changes_requested(self, mock_send):
        ms = MissionState(
            waiting_approval={
                "verdict": "CHANGES_REQUESTED",
                "task_id": "1.1", "task_title": "Fix bug",
            },
            waiting_notified=False,
        )
        telegram_listener.check_waiting_approval("tok", "1", mission_state=ms)
        msg = mock_send[0]
        assert "CHANGES REQUESTED" in msg
        assert "/retry" in msg
        assert "/skip" in msg
        assert "/approve" in msg
        assert "/abort" in msg

    def test_other_verdict(self, mock_send):
        ms = MissionState(
            waiting_approval={
                "verdict": "APPROVED",
                "task_id": "2.1", "task_title": "Add feature",
            },
            waiting_notified=False,
        )
        telegram_listener.check_waiting_approval("tok", "1", mission_state=ms)
        msg = mock_send[0]
        assert "/approve" in msg
        assert "/reject" in msg

    def test_sets_notified_flag(self, mock_send):
        ms = MissionState(
            waiting_approval={"verdict": "APPROVED", "task_id": "1.1", "task_title": "T"},
            waiting_notified=False,
        )
        telegram_listener.check_waiting_approval("tok", "1", mission_state=ms)
        assert ms.waiting_notified is True


# Area 5: poll_loop


class _PollBreak(Exception):
    pass


class TestPollLoop:

    def test_dispatches_command(self, monkeypatch, tmp_path):
        calls = []

        def fake_get_updates(token, offset, timeout=30):
            if not calls:
                calls.append(True)
                return [{
                    "update_id": 100,
                    "message": {
                        "chat": {"id": 42},
                        "text": "/status",
                    },
                }]
            raise _PollBreak()

        handled = []
        monkeypatch.setattr(telegram_api, "get_updates", fake_get_updates)
        monkeypatch.setattr(telegram_listener, "handle_command",
                            lambda *a, **kw: handled.append(a))
        monkeypatch.setattr(telegram_listener, "check_waiting_approval",
                            lambda *a, **kw: None)

        with pytest.raises(_PollBreak):
            telegram_listener.poll_loop("tok", "42", tmp_path)

        assert len(handled) == 1
        assert handled[0][3] == tmp_path

    def test_filters_wrong_chat(self, monkeypatch, tmp_path):
        call_count = [0]

        def fake_get_updates(token, offset, timeout=30):
            call_count[0] += 1
            if call_count[0] == 1:
                return [{
                    "update_id": 100,
                    "message": {
                        "chat": {"id": 999},
                        "text": "/status",
                    },
                }]
            raise _PollBreak()

        handled = []
        monkeypatch.setattr(telegram_api, "get_updates", fake_get_updates)
        monkeypatch.setattr(telegram_listener, "handle_command",
                            lambda *a, **kw: handled.append(a))
        monkeypatch.setattr(telegram_listener, "check_waiting_approval",
                            lambda *a, **kw: None)

        with pytest.raises(_PollBreak):
            telegram_listener.poll_loop("tok", "42", tmp_path)

        assert len(handled) == 0

    def test_advances_offset(self, monkeypatch, tmp_path):
        call_count = [0]
        offsets = []

        def fake_get_updates(token, offset, timeout=30):
            offsets.append(offset)
            call_count[0] += 1
            if call_count[0] == 1:
                return [
                    {"update_id": 100, "message": {"chat": {"id": 42}, "text": "/a"}},
                    {"update_id": 101, "message": {"chat": {"id": 42}, "text": "/b"}},
                ]
            raise _PollBreak()

        monkeypatch.setattr(telegram_api, "get_updates", fake_get_updates)
        monkeypatch.setattr(telegram_listener, "handle_command",
                            lambda *a, **kw: None)
        monkeypatch.setattr(telegram_listener, "check_waiting_approval",
                            lambda *a, **kw: None)

        with pytest.raises(_PollBreak):
            telegram_listener.poll_loop("tok", "42", tmp_path)

        assert offsets[0] == 0
        assert offsets[1] == 102


# Area 6: start_listener


class TestStartListener:

    def test_returns_daemon_thread(self, monkeypatch):
        monkeypatch.setattr(telegram_listener, "poll_loop",
                            lambda *a, **kw: None)
        monkeypatch.setattr(telegram_listener, "CLAUDE_CMD", "/bin/claude")
        q = queue.Queue()
        ms = MissionState()
        t = telegram_listener.start_listener("tok", "1", q, ms)
        t.join(timeout=2)
        assert t.daemon is True

    def test_sets_claude_cmd(self, monkeypatch):
        monkeypatch.setattr(telegram_listener, "poll_loop",
                            lambda *a, **kw: None)
        monkeypatch.setattr(telegram_listener, "CLAUDE_CMD", None)
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/claude")
        q = queue.Queue()
        ms = MissionState()
        t = telegram_listener.start_listener("tok", "1", q, ms)
        t.join(timeout=2)
        assert telegram_listener.CLAUDE_CMD == "/usr/bin/claude"

    def test_preserves_existing_claude_cmd(self, monkeypatch):
        monkeypatch.setattr(telegram_listener, "poll_loop",
                            lambda *a, **kw: None)
        monkeypatch.setattr(telegram_listener, "CLAUDE_CMD", "/existing/claude")
        q = queue.Queue()
        ms = MissionState()
        t = telegram_listener.start_listener("tok", "1", q, ms)
        t.join(timeout=2)
        assert telegram_listener.CLAUDE_CMD == "/existing/claude"


# Area 7: _safe_chunk_boundary


class TestSafeChunkBoundary:

    def test_boundary_past_end(self):
        assert telegram_api._safe_chunk_boundary("abc", 10) == 3

    def test_combining_mark_fallback(self):
        # single base char + combining acute (U+0301): boundary=1 hits combining,
        # backs to 0, boundary<=0 triggers fallback to original (1)
        text = "a" + chr(0x0301) + "b"
        result = telegram_api._safe_chunk_boundary(text, 1)
        assert result == 1

    def test_combining_in_longer_text(self):
        # "x" + "x" + combining acute (U+0301) + "y"
        text = "xx" + chr(0x0301) + "y"
        result = telegram_api._safe_chunk_boundary(text, 2)
        assert result == 1

    def test_all_combining_fallback(self):
        text = chr(0x0300) + chr(0x0301) + chr(0x0302)
        result = telegram_api._safe_chunk_boundary(text, 2)
        assert result == 2

    def test_plain_ascii_unchanged(self):
        assert telegram_api._safe_chunk_boundary("hello world", 5) == 5


# Area 8: helper functions


class TestHelpers:

    def test_project_color_empty(self):
        assert telegram_api._project_color("") == ""

    def test_project_color_deterministic(self):
        c1 = telegram_api._project_color("myproject:branch")
        c2 = telegram_api._project_color("myproject:branch")
        assert c1 == c2
        assert c1 in PROJECT_COLORS

    def test_set_msg_prefix_with_tag(self):
        telegram_api._set_msg_prefix("proj:branch")
        prefix = _msg_ctx.prefix
        assert "[proj]" in prefix
        assert any(c in prefix for c in PROJECT_COLORS)

    def test_set_msg_prefix_empty(self):
        telegram_api._set_msg_prefix("")
        assert _msg_ctx.prefix == ""

    def test_extract_changes_required_with_section(self):
        nl = chr(10)
        audit = f"# Review{nl}Some intro{nl}## Cambios Requeridos{nl}- fix X{nl}- fix Y{nl}# Next Section{nl}other stuff"
        result = telegram_listener._extract_changes_required(audit)
        assert result == f"What needs fixing:{nl}- fix X{nl}- fix Y"

    def test_extract_changes_required_no_section(self):
        audit = "Just some review text without any special headers."
        result = telegram_listener._extract_changes_required(audit)
        assert result == audit
