import queue
from unittest.mock import MagicMock, patch

import pytest

from src.core.notification import notify, set_notify_prefix
from src.core.state import update_state, _apply_gate_change
from src.mission.signals import check_signals
from src.mission.human_input import (
    HumanInput, _handle_gate, _handle_retry, _parse_stdin_line,
    _start_stdin_listener,
)
from src.agent.loop import DONE_SIGNAL
from src.core.block_state import BlockState


# --- _handle_retry / _handle_gate ---


def test_handle_retry_no_feedback():
    assert _handle_retry("/retry") == {"cmd": "retry", "feedback": ""}


def test_handle_retry_with_feedback():
    assert _handle_retry("/retry fix the tests") == {"cmd": "retry", "feedback": "fix the tests"}


def test_handle_gate_on():
    assert _handle_gate("/gate on") == {"cmd": "gate", "mode": "manual"}


def test_handle_gate_off():
    assert _handle_gate("/gate off") == {"cmd": "gate", "mode": "auto"}


def test_handle_gate_invalid():
    assert _handle_gate("/gate banana") is None


def test_handle_gate_no_arg():
    assert _handle_gate("/gate") is None


# --- _parse_stdin_line ---


def test_parse_stdin_line_whitespace_only():
    assert _parse_stdin_line("  \t  ") is None


def test_parse_stdin_line_unknown_slash_treated_as_answer():
    result = _parse_stdin_line("/unknown")
    assert result == {"cmd": "answer", "text": "/unknown"}


# --- update_state ---


def test_update_state_reads_gate_from_file(tmp_path):
    (tmp_path / "_gate_mode").write_text("manual", encoding="utf-8")
    update_state("spec", tmp_path)
    import json
    state = json.loads((tmp_path / "_state.json").read_text(encoding="utf-8"))
    assert state["gate"] == "manual"
    assert state["phase"] == "spec"


def test_update_state_missing_gate_file_defaults_auto(tmp_path):
    update_state("plan", tmp_path)
    import json
    state = json.loads((tmp_path / "_state.json").read_text(encoding="utf-8"))
    assert state["gate"] == "auto"


def test_update_state_explicit_gate_overrides_file(tmp_path):
    (tmp_path / "_gate_mode").write_text("manual", encoding="utf-8")
    update_state("spec", tmp_path, gate="auto")
    import json
    state = json.loads((tmp_path / "_state.json").read_text(encoding="utf-8"))
    assert state["gate"] == "auto"


# --- _apply_gate_change ---


def test_apply_gate_change_with_mission_state(tmp_path):
    ms = MagicMock()
    _apply_gate_change("manual", tmp_path, ms)
    assert (tmp_path / "_gate_mode").read_text(encoding="utf-8") == "manual"
    assert ms.gate == "manual"


# --- check_signals ---


def test_check_signals_unknown_command_requeued(tmp_path, monkeypatch):
    monkeypatch.setattr("src.core.notification._notify_backend", lambda msg, **kw: None)
    requeued = []

    class FakeQueue:
        def __init__(self):
            self._items = [{"cmd": "some_future_cmd"}]
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

    ms = MagicMock()
    blocked = BlockState()
    result = check_signals(FakeQueue(), tmp_path, ms, blocked)
    assert result is True
    assert len(requeued) == 1
    assert requeued[0]["cmd"] == "some_future_cmd"


def test_check_signals_unknown_command_is_not_reprocessed_same_tick(tmp_path, monkeypatch):
    monkeypatch.setattr("src.core.notification._notify_backend", lambda msg, **kw: None)

    class RequeueingQueue:
        def __init__(self):
            self._items = [{"cmd": "approve"}]
            self.gets = 0
            self.requeued = []

        def get_nowait(self):
            self.gets += 1
            if self.gets > 2:
                raise AssertionError("deferred command was read again in the same tick")
            if self._items:
                return self._items.pop(0)
            raise queue.Empty

        def get(self, timeout=None):
            raise queue.Empty

        def put(self, item):
            self.requeued.append(item)
            self._items.append(item)

    cq = RequeueingQueue()
    ms = MagicMock()
    blocked = BlockState()
    result = check_signals(cq, tmp_path, ms, blocked)
    assert result is True
    assert cq.gets == 2
    assert cq.requeued == [{"cmd": "approve"}]


def test_check_signals_gate_during_pause(tmp_path, monkeypatch):
    monkeypatch.setattr("src.core.notification._notify_backend", lambda msg, **kw: None)
    cq = queue.Queue()
    cq.put({"cmd": "pause"})
    cq.put({"cmd": "gate", "mode": "manual"})
    cq.put({"cmd": "resume"})
    ms = MagicMock()
    blocked = BlockState()
    (tmp_path / "_gate_mode").write_text("auto", encoding="utf-8")
    result = check_signals(cq, tmp_path, ms, blocked)
    assert result is True
    assert (tmp_path / "_gate_mode").read_text(encoding="utf-8") == "manual"


def test_check_signals_multiple_commands(tmp_path, monkeypatch):
    monkeypatch.setattr("src.core.notification._notify_backend", lambda msg, **kw: None)
    cq = queue.Queue()
    cq.put({"cmd": "gate", "mode": "manual"})
    cq.put({"cmd": "gate", "mode": "auto"})
    ms = MagicMock()
    blocked = BlockState()
    (tmp_path / "_gate_mode").write_text("auto", encoding="utf-8")
    result = check_signals(cq, tmp_path, ms, blocked)
    assert result is True
    assert (tmp_path / "_gate_mode").read_text(encoding="utf-8") == "auto"


# --- set_notify_prefix / notify ---


def test_set_notify_prefix(monkeypatch):
    calls = []
    monkeypatch.setattr("src.core.notification._notify_backend", lambda msg, **kw: calls.append((msg, kw)))
    set_notify_prefix("[TEST]")
    notify("hello")
    assert len(calls) == 1
    assert calls[0][1]["prefix"] == "[TEST]"

    set_notify_prefix("")
    notify("world")
    assert calls[1][1]["prefix"] == ""


# --- _start_stdin_listener ---


def test_start_stdin_listener_skips_non_tty(monkeypatch):
    monkeypatch.setattr("sys.stdin", MagicMock(isatty=lambda: False))
    cq = queue.Queue()
    _start_stdin_listener(cq)


# --- HumanInput ---


def test_human_input_answer():
    cq = queue.Queue()
    blocked = BlockState()
    hi = HumanInput(cq, blocked)
    cq.put({"cmd": "answer", "text": "my response"})
    result = hi("What do you think?")
    assert result == "my response"


def test_human_input_done():
    cq = queue.Queue()
    blocked = BlockState()
    hi = HumanInput(cq, blocked)
    cq.put({"cmd": "done"})
    result = hi("Any more input?")
    assert result == DONE_SIGNAL


def test_human_input_abort():
    cq = queue.Queue()
    blocked = BlockState()
    hi = HumanInput(cq, blocked)
    cq.put({"cmd": "abort"})
    result = hi("Continue?")
    assert result == DONE_SIGNAL
    assert blocked.value == "user_abort"


def test_human_input_skips_non_answer_commands():
    cq = queue.Queue()
    blocked = BlockState()
    hi = HumanInput(cq, blocked)
    cq.put({"cmd": "gate", "mode": "manual"})
    cq.put({"cmd": "answer", "text": "actual answer"})
    result = hi("Question?")
    assert result == "actual answer"
    requeued = cq.get()
    assert requeued["cmd"] == "gate"


def test_human_input_defers_non_answer_command_until_answer_arrives():
    class DelayedAnswerQueue:
        def __init__(self):
            self._items = [{"cmd": "gate", "mode": "manual"}]
            self._delayed_answer = {"cmd": "answer", "text": "actual answer"}
            self.gets = 0
            self.requeued = []

        def get(self, timeout=None):
            self.gets += 1
            if self.gets > 3:
                raise AssertionError("deferred command was read again before an answer")
            if self._items:
                return self._items.pop(0)
            if self._delayed_answer is not None:
                answer = self._delayed_answer
                self._delayed_answer = None
                return answer
            raise queue.Empty

        def put(self, item):
            self.requeued.append(item)
            self._items.append(item)

    cq = DelayedAnswerQueue()
    blocked = BlockState()
    hi = HumanInput(cq, blocked)
    result = hi("Question?")
    assert result == "actual answer"
    assert cq.gets == 2
    assert cq.requeued == [{"cmd": "gate", "mode": "manual"}]


def test_human_input_with_log():
    cq = queue.Queue()
    blocked = BlockState()
    logged = []
    hi = HumanInput(cq, blocked, log=lambda msg: logged.append(msg))
    cq.put({"cmd": "answer", "text": "hello"})
    hi("Question?")
    assert any("hello" in m for m in logged)


def test_human_input_done_with_log():
    cq = queue.Queue()
    blocked = BlockState()
    logged = []
    hi = HumanInput(cq, blocked, log=lambda msg: logged.append(msg))
    cq.put({"cmd": "done"})
    hi("Question?")
    assert any("/done" in m for m in logged)
