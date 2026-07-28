"""Deterministic tests for the single-mission Telegram adapter.

Transport retry/chunking and process-lock behavior have dedicated test modules.
This file exercises the listener boundary: authorization, command dispatch,
correlation, durable acknowledgement ordering, and lifecycle.
"""

from __future__ import annotations

import queue
import threading
from pathlib import Path

import pytest

from src.core.state import ControlState, InteractionKind, MissionState
from src.integrations import telegram_api, telegram_commands, telegram_listener
from src.integrations.telegram_api import SendResult
from src.integrations.telegram_listener import (
    HELP_TEXT,
    ListenerHandle,
    ListenerHealth,
    ListenerStatus,
)
from src.mission.control import CommandEnvelope, CommandRouter


class FakeQuestionService:
    def __init__(self, *, accepted: bool = True, immediate: str | None = None) -> None:
        self.accepted = accepted
        self.immediate = immediate
        self.questions: list[str] = []
        self.callback = None

    def ask(self, question: str, callback) -> bool:
        self.questions.append(question)
        self.callback = callback
        if self.immediate is not None:
            callback(self.immediate)
        return self.accepted


@pytest.fixture
def sent_messages(monkeypatch):
    messages: list[str] = []

    def fake_send(token, chat_id, text, **kwargs):
        del token, chat_id, kwargs
        messages.append(text)
        return SendResult(ok=True, chunks_sent=1, attempts=1)

    monkeypatch.setattr(telegram_api, "send_message", fake_send)
    return messages


def _dispatch(
    text: str,
    harness: Path,
    *,
    state: MissionState | None = None,
    command_queue: queue.Queue | None = None,
    service: FakeQuestionService | None = None,
    update_id: int = 1,
) -> tuple[MissionState, queue.Queue, FakeQuestionService]:
    state = state or MissionState()
    command_queue = command_queue or queue.Queue()
    service = service or FakeQuestionService()
    telegram_listener.handle_command(
        "token",
        "123",
        text,
        harness,
        router=CommandRouter(state, command_queue),
        mission_state=state,
        question_service=service,
        update_id=update_id,
    )
    return state, command_queue, service


class TestCommandParsingAndReads:
    def test_parse_standard_bot_username_suffix(self):
        assert telegram_listener._parse_command(" /STATUS@HarnessBot  now ") == (
            "/status",
            ["now"],
        )

    @pytest.mark.parametrize("text", ["", "plain text", "  not-a-command  "])
    def test_parse_ignores_non_commands(self, text):
        assert telegram_listener._parse_command(text) is None

    def test_bot_username_never_selects_another_mission(self, tmp_path, sent_messages):
        (tmp_path / "spec.md").write_text("current mission only", encoding="utf-8")

        _dispatch("/spec@SomeOtherName", tmp_path)

        assert sent_messages == ["--- spec.md ---\ncurrent mission only"]

    @pytest.mark.parametrize("command", ["/help", "/start"])
    def test_help_commands(self, command, tmp_path, sent_messages):
        _dispatch(command, tmp_path)
        assert sent_messages == [HELP_TEXT]
        assert "current mission only" in sent_messages[0]

    def test_unknown_command_includes_help(self, tmp_path, sent_messages):
        _dispatch("/unknown", tmp_path)
        assert sent_messages[0].startswith("Unknown command: /unknown")
        assert HELP_TEXT in sent_messages[0]

    def test_non_command_is_ignored(self, tmp_path, sent_messages):
        _dispatch("hello", tmp_path)
        assert sent_messages == []

    def test_status_is_available_after_abort(self, tmp_path, sent_messages):
        state = MissionState(
            phase="review",
            task_id="2.1",
            task_title="Check result",
            task_num=2,
            task_count=3,
            completed=1,
            gate="manual",
            control_state=ControlState.ABORTED,
        )

        _dispatch("/status", tmp_path, state=state)

        message = sent_messages[0]
        assert "Task 2/3: 2.1" in message
        assert "Check result" in message
        assert "Control: aborted" in message

    def test_status_uses_progress_file_when_activity_is_empty(
        self, tmp_path, sent_messages
    ):
        (tmp_path / "_progress.txt").write_text("running unit tests", encoding="utf-8")
        state = MissionState(phase="implement", task_num=1, task_count=1)

        _dispatch("/status", tmp_path, state=state)

        assert "Last activity: running unit tests" in sent_messages[0]

    def test_log_returns_only_last_thirty_lines(self, tmp_path, sent_messages):
        (tmp_path / "mission.log").write_text(
            "\n".join(f"line {number}" for number in range(35)),
            encoding="utf-8",
        )

        _dispatch("/log", tmp_path)

        assert "line 4\n" not in f"{sent_messages[0]}\n"
        assert sent_messages[0].startswith("line 5\n")
        assert sent_messages[0].endswith("line 34")

    @pytest.mark.parametrize("argument", ["", "0", "51", "many", "1 2", "-1"])
    def test_verbose_rejects_values_outside_one_to_fifty(
        self, argument, tmp_path, sent_messages
    ):
        telegram_commands.cmd_verbose(
            "token", "123", argument.split(), tmp_path, mission_state=MissionState()
        )
        assert sent_messages == ["Usage: /verbose <1-50>"]

    @pytest.mark.parametrize("count", [1, 50])
    def test_verbose_accepts_boundary_values(self, count, tmp_path, sent_messages):
        (tmp_path / "mission.log").write_text(
            "\n".join(f"12:00  > activity {number}" for number in range(60)),
            encoding="utf-8",
        )

        telegram_commands.cmd_verbose(
            "token", "123", [str(count)], tmp_path, mission_state=MissionState()
        )

        assert len(sent_messages[0].splitlines()) == count
        assert sent_messages[0].endswith("activity 59")

    def test_artifact_rejects_extra_arguments(self, tmp_path, sent_messages):
        (tmp_path / "plan.md").write_text("secret plan", encoding="utf-8")
        _dispatch("/plan extra", tmp_path)
        assert sent_messages == ["Usage: /plan"]

    def test_large_artifact_is_bounded_to_one_telegram_message(
        self, tmp_path, sent_messages,
    ):
        (tmp_path / "spec.md").write_text("x" * 10_000, encoding="utf-8")

        _dispatch("/spec", tmp_path)

        assert len(sent_messages) == 1
        assert len(sent_messages[0]) <= telegram_api.TELEGRAM_MAX_MSG
        assert "truncated" in sent_messages[0]


class TestRouterAndAcknowledgements:
    def test_pause_ack_matches_enqueued_action(self, tmp_path, sent_messages):
        state, command_queue, _ = _dispatch("/pause", tmp_path, update_id=17)

        assert sent_messages == ["pause requested"]
        assert state.control_state is ControlState.PAUSE_PENDING
        envelope = command_queue.get_nowait()
        assert isinstance(envelope, CommandEnvelope)
        assert envelope.name == "pause"
        assert envelope.update_id == 17
        assert envelope.source == "telegram"

    def test_invalid_command_is_rejected_before_queueing(self, tmp_path, sent_messages):
        _, command_queue, _ = _dispatch("/resume", tmp_path)
        assert sent_messages == ["mission is not paused"]
        assert command_queue.empty()

    @pytest.mark.parametrize(
        ("command", "expected"),
        [
            ("/pause now", "/pause does not accept arguments"),
            ("/gate", "usage: /gate on|off"),
            ("/gate maybe", "usage: /gate on|off"),
            ("/abort later", "/abort does not accept arguments"),
        ],
    )
    def test_invalid_arguments_never_reach_queue(
        self, command, expected, tmp_path, sent_messages
    ):
        _, command_queue, _ = _dispatch(command, tmp_path)
        assert sent_messages == [expected]
        assert command_queue.empty()

    def test_gate_off_does_not_resolve_open_approval(self, tmp_path, sent_messages):
        state = MissionState(gate="manual")
        interaction = state.open_interaction(
            InteractionKind.APPROVAL, task_id="1.1", prompt="Approve task?"
        )

        state, command_queue, _ = _dispatch("/gate off", tmp_path, state=state)

        assert sent_messages == ["gate change accepted (auto)"]
        assert state.get_interaction() == interaction
        envelope = command_queue.get_nowait()
        assert envelope.name == "gate"
        assert envelope.args == {"mode": "auto"}

    def test_grill_answer_requires_delivered_question(self, tmp_path, sent_messages):
        state = MissionState()
        state.open_interaction(InteractionKind.GRILL, prompt="Which database?")

        _, command_queue, _ = _dispatch(
            "/answer sqlite", tmp_path, state=state, update_id=20
        )

        assert sent_messages == ["the current question has not been delivered yet"]
        assert command_queue.empty()

    def test_first_interaction_response_wins_and_is_correlated(
        self, tmp_path, sent_messages
    ):
        state = MissionState()
        interaction = state.open_interaction(
            InteractionKind.GRILL, task_id="1.2", prompt="Which database?"
        )
        state.mark_interaction_notified(interaction.id)
        command_queue: queue.Queue = queue.Queue()

        _dispatch(
            "/answer sqlite",
            tmp_path,
            state=state,
            command_queue=command_queue,
            update_id=21,
        )
        _dispatch(
            "/done",
            tmp_path,
            state=state,
            command_queue=command_queue,
            update_id=22,
        )

        assert sent_messages == [
            "answer accepted",
            "this interaction already has an accepted response",
        ]
        envelope = command_queue.get_nowait()
        assert envelope.name == "answer"
        assert envelope.args == {"text": "sqlite"}
        assert envelope.update_id == 21
        assert envelope.interaction_id == interaction.id
        assert command_queue.empty()

    def test_changes_requested_force_approval_has_truthful_ack(
        self, tmp_path, sent_messages
    ):
        state = MissionState()
        interaction = state.open_interaction(
            InteractionKind.REVIEW_DECISION,
            task_id="2.1",
            prompt="Reviewer requested changes",
        )

        _, command_queue, _ = _dispatch(
            "/approve", tmp_path, state=state, update_id=31
        )

        assert sent_messages == ["force-approval accepted"]
        envelope = command_queue.get_nowait()
        assert envelope.interaction_id == interaction.id
        assert envelope.name == "approve"


class TestInteractionDelivery:
    def test_marks_notified_only_after_complete_send(self, monkeypatch):
        state = MissionState()
        interaction = state.open_interaction(
            InteractionKind.GRILL, task_id="1.1", prompt="Actual grill question"
        )
        results = iter(
            [
                SendResult(ok=False, chunks_sent=0, attempts=1),
                SendResult(ok=True, chunks_sent=1, attempts=1),
            ]
        )
        delivered: list[str] = []

        def fake_send(token, chat_id, text):
            del token, chat_id
            delivered.append(text)
            return next(results)

        monkeypatch.setattr(telegram_api, "send_message", fake_send)

        assert not telegram_listener.notify_pending_interaction("tok", "123", state)
        assert state.get_interaction().notified is False
        assert telegram_listener.notify_pending_interaction("tok", "123", state)
        assert state.get_interaction().notified is True
        assert not telegram_listener.notify_pending_interaction("tok", "123", state)
        assert delivered == ["Actual grill question", "Actual grill question"]


class TestPrivateChatAuthorization:
    @staticmethod
    def update(
        *,
        chat_id=123,
        sender_id=123,
        chat_type="private",
        text=" /status ",
    ):
        return {
            "update_id": 1,
            "message": {
                "chat": {"id": chat_id, "type": chat_type},
                "from": {"id": sender_id},
                "text": text,
            },
        }

    def test_accepts_only_configured_private_user(self):
        assert telegram_listener._authorized_text(self.update(), "123") == "/status"

    @pytest.mark.parametrize(
        "update",
        [
            update(chat_id=999),
            update(sender_id=999),
            update(chat_type="group"),
            update(text="   "),
            {"update_id": 1},
            {"update_id": 1, "message": {"chat": {}, "from": {}}},
        ],
    )
    def test_rejects_wrong_or_incomplete_message(self, update):
        assert telegram_listener._authorized_text(update, "123") is None


class RecordingOffsetStore:
    def __init__(self, initial: int = 10) -> None:
        self.initial = initial
        self.writes: list[int] = []

    def load_or_synchronize(self, fetch_updates):
        del fetch_updates
        return self.initial

    def write(self, value: int) -> None:
        self.writes.append(value)


def _private_update(update_id: int, text: str = "/status", *, sender=123):
    return {
        "update_id": update_id,
        "message": {
            "chat": {"id": 123, "type": "private"},
            "from": {"id": sender},
            "text": text,
        },
    }


class TestPollingSemantics:
    def test_pending_prompt_send_failure_does_not_block_command_polling(
        self, tmp_path, monkeypatch
    ):
        stop_event = threading.Event()
        polled = []

        def fail_prompt(*_args, **_kwargs):
            raise telegram_api.TelegramAPIError(
                "temporary send failure",
                error_code=503,
                retryable=True,
            )

        def get_updates(*_args, **_kwargs):
            polled.append(True)
            stop_event.set()
            return []

        monkeypatch.setattr(telegram_listener, "notify_pending_interaction", fail_prompt)
        monkeypatch.setattr(telegram_api, "get_updates", get_updates)

        telegram_listener.poll_loop(
            "token",
            "123",
            tmp_path,
            router=CommandRouter(MissionState(), queue.Queue()),
            mission_state=MissionState(),
            question_service=FakeQuestionService(),
            offset_store=RecordingOffsetStore(),
            stop_event=stop_event,
            health=ListenerHealth(),
            initial_offset=10,
        )

        assert polled == [True]

    def test_persists_before_dispatch_and_isolates_handler_failures(
        self, tmp_path, monkeypatch
    ):
        stop_event = threading.Event()
        health = ListenerHealth()
        store = RecordingOffsetStore()
        events: list[tuple[str, int]] = []
        logs: list[str] = []

        def fake_get_updates(token, offset, timeout, **kwargs):
            del token, timeout, kwargs
            assert offset == 10
            return [
                _private_update(10, "/broken"),
                _private_update(11, sender=999),
                _private_update(12, "/status"),
            ]

        original_write = store.write

        def recording_write(value):
            original_write(value)
            events.append(("write", value))

        store.write = recording_write

        def fake_handle(*args, update_id, **kwargs):
            del args, kwargs
            events.append(("handle", update_id))
            if update_id == 10:
                raise RuntimeError("defective handler")
            stop_event.set()

        monkeypatch.setattr(telegram_api, "get_updates", fake_get_updates)
        monkeypatch.setattr(telegram_listener, "handle_command", fake_handle)

        telegram_listener.poll_loop(
            "token",
            "123",
            tmp_path,
            router=CommandRouter(MissionState(), queue.Queue()),
            mission_state=MissionState(),
            question_service=FakeQuestionService(),
            offset_store=store,
            stop_event=stop_event,
            health=health,
            on_log=logs.append,
        )

        assert events == [
            ("write", 11),
            ("handle", 10),
            ("write", 12),
            ("write", 13),
            ("handle", 12),
        ]
        assert store.writes == [11, 12, 13]
        assert any("command 10 failed" in line for line in logs)
        assert health.snapshot().status is ListenerStatus.STOPPED

    def test_offset_failure_prevents_dispatch(self, tmp_path, monkeypatch):
        stop_event = threading.Event()
        health = ListenerHealth()
        called: list[int] = []

        class FailingStore(RecordingOffsetStore):
            def write(self, value):
                del value
                stop_event.set()
                raise OSError("disk full")

        monkeypatch.setattr(
            telegram_api,
            "get_updates",
            lambda *args, **kwargs: [_private_update(10, "/abort")],
        )
        monkeypatch.setattr(
            telegram_listener,
            "handle_command",
            lambda *args, update_id, **kwargs: called.append(update_id),
        )

        telegram_listener.poll_loop(
            "token",
            "123",
            tmp_path,
            router=CommandRouter(MissionState(), queue.Queue()),
            mission_state=MissionState(),
            question_service=FakeQuestionService(),
            offset_store=FailingStore(),
            stop_event=stop_event,
            health=health,
        )

        assert called == []
        assert "could not persist update offset" in health.snapshot().last_error

    def test_persistent_offset_failure_uses_bounded_backoff(self, tmp_path, monkeypatch):
        class ControlledStop:
            def __init__(self):
                self.stopped = False
                self.waits = []

            def is_set(self):
                return self.stopped

            def set(self):
                self.stopped = True

            def wait(self, delay):
                self.waits.append(delay)
                if len(self.waits) == 3:
                    self.stopped = True
                return self.stopped

        class FailingStore:
            def write(self, _value):
                raise OSError("disk full")

        stop = ControlledStop()
        polls = []
        monkeypatch.setattr(
            telegram_api,
            "get_updates",
            lambda *_args, **_kwargs: polls.append(True) or [_private_update(10, "/abort")],
        )

        telegram_listener.poll_loop(
            "token",
            "123",
            tmp_path,
            router=CommandRouter(MissionState(), queue.Queue()),
            mission_state=MissionState(),
            question_service=FakeQuestionService(),
            offset_store=FailingStore(),
            stop_event=stop,
            health=ListenerHealth(),
            initial_offset=10,
        )

        assert polls == [True, True, True]
        assert stop.waits == [0.5, 1.0, 2.0]


class TestListenerLifecycle:
    def test_stop_is_idempotent(self):
        stop_event = threading.Event()
        health = ListenerHealth()
        worker = threading.Thread(target=stop_event.wait, daemon=True)
        worker.start()
        handle = ListenerHandle(worker, stop_event, health)

        assert handle.stop(timeout=1)
        assert handle.stop(timeout=1)
        assert not handle.is_alive
        assert health.snapshot().status is ListenerStatus.STOPPED

    @pytest.mark.parametrize(("token", "chat_id"), [("", "123"), ("tok", "")])
    def test_start_listener_rejects_partial_configuration(self, token, chat_id, tmp_path):
        with pytest.raises(ValueError):
            telegram_listener.start_listener(
                token,
                chat_id,
                queue.Queue(),
                MissionState(),
                harness=tmp_path,
                question_service=FakeQuestionService(),
            )

    def test_start_listener_synchronizes_before_starting_thread(self, tmp_path, monkeypatch):
        events = []

        class Store:
            def load_or_synchronize(self, _fetch_updates):
                events.append("sync")
                return 44

        class Thread:
            def __init__(self, *, target, kwargs, daemon, name):
                del target, daemon, name
                self.kwargs = kwargs

            def start(self):
                events.append(("start", self.kwargs["initial_offset"]))

            def is_alive(self):
                return True

        monkeypatch.setattr(telegram_listener.threading, "Thread", Thread)

        telegram_listener.start_listener(
            "token",
            "123",
            queue.Queue(),
            MissionState(),
            harness=tmp_path,
            question_service=FakeQuestionService(),
            offset_store=Store(),
        )

        assert events == ["sync", ("start", 44)]

    def test_startup_sync_retries_transient_telegram_failures(self, monkeypatch):
        attempts = 0

        class Store:
            def load_or_synchronize(self, _fetch_updates):
                nonlocal attempts
                attempts += 1
                if attempts < 3:
                    raise telegram_api.TelegramAPIError(
                        "temporary",
                        error_code=503,
                        retryable=True,
                    )
                return 9

        sleeps = []
        monkeypatch.setattr(telegram_listener.time, "sleep", sleeps.append)

        assert telegram_listener._synchronize_startup_offset("token", Store()) == 9
        assert attempts == 3
        assert sleeps == [0.5, 1.0]


class TestAskBridge:
    def test_accepted_question_sends_thinking_then_async_answer(
        self, tmp_path, sent_messages
    ):
        service = FakeQuestionService(accepted=True)

        _dispatch("/ask where is config", tmp_path, service=service)

        assert service.questions == ["where is config"]
        assert sent_messages == ["Thinking..."]
        service.callback("Config is in src/config.py")
        assert sent_messages == ["Thinking...", "Config is in src/config.py"]

    def test_immediate_service_response_cannot_overtake_thinking(
        self, tmp_path, sent_messages
    ):
        service = FakeQuestionService(accepted=True, immediate="Fast answer")
        _dispatch("/ask quick question", tmp_path, service=service)
        assert sent_messages == ["Thinking...", "Fast answer"]

    def test_busy_or_invalid_question_does_not_send_thinking(
        self, tmp_path, sent_messages
    ):
        service = FakeQuestionService(accepted=False, immediate="Service busy")
        _dispatch("/ask another question", tmp_path, service=service)
        assert sent_messages == ["Service busy"]

    def test_ask_is_disabled_after_abort_request(self, tmp_path, sent_messages):
        service = FakeQuestionService()
        state = MissionState(control_state=ControlState.ABORT_PENDING)
        _dispatch("/ask what changed", tmp_path, state=state, service=service)
        assert service.questions == []
        assert sent_messages == [
            "Code questions are disabled after abort is requested."
        ]
