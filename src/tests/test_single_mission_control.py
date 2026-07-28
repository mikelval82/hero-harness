from __future__ import annotations

import queue
import threading
import time
from types import SimpleNamespace

import pytest

from src.agent.loop import ABORT_SIGNAL
from src.core.block_state import BlockState
from src.core.state import ControlState, InteractionKind, MissionState
from src.core.context import PhaseName
from src.mission.hitl import HitlReviewer
from src.mission.control import CommandRouter
from src.mission.human_input import HumanInput
from src.mission.runner import MissionRunner
from src.mission.signals import check_signals
from src.mission.task_executor import TaskExecutor


_MUTATOR_ARGS = {
    "pause": [],
    "resume": [],
    "abort": [],
    "gate": ["on"],
    "answer": ["answer"],
    "done": [],
    "approve": [],
    "reject": [],
    "retry": ["fix it"],
    "skip": [],
}


@pytest.mark.parametrize(
    ("context", "valid_commands"),
    [
        ("running", {"pause", "abort", "gate"}),
        ("pause_pending", {"resume", "abort", "gate"}),
        ("paused", {"resume", "abort", "gate"}),
        ("abort_pending", set()),
        ("aborted", set()),
        ("completed", set()),
        ("failed", set()),
        ("grill", {"answer", "done", "abort", "gate"}),
        ("approval", {"approve", "reject", "abort", "gate"}),
        ("review_decision", {"retry", "skip", "approve", "abort", "gate"}),
    ],
)
@pytest.mark.parametrize("command", tuple(_MUTATOR_ARGS))
def test_complete_mutating_command_state_matrix(context, valid_commands, command):
    state = MissionState()
    if context in {
        "pause_pending",
        "paused",
        "abort_pending",
        "aborted",
        "completed",
        "failed",
    }:
        state.set_control_state(ControlState(context))
    elif context in {"grill", "approval", "review_decision"}:
        state.open_interaction(InteractionKind(context))
    commands = queue.Queue()

    outcome = CommandRouter(state, commands).route(
        command,
        _MUTATOR_ARGS[command],
        update_id=f"{context}:{command}",
        source="stdin",
    )

    assert outcome.accepted is (command in valid_commands)
    assert commands.empty() is (command not in valid_commands)


@pytest.mark.parametrize(
    ("command", "args"),
    [
        ("pause", ["now"]),
        ("resume", ["now"]),
        ("abort", ["now"]),
        ("approve", ["because"]),
        ("skip", ["because"]),
        ("done", ["now"]),
    ],
)
def test_no_argument_commands_reject_extra_text(command, args):
    state = MissionState()
    commands = queue.Queue()
    router = CommandRouter(state, commands)
    if command == "resume":
        state.set_control_state(ControlState.PAUSED)
    elif command in {"approve", "skip"}:
        kind = InteractionKind.APPROVAL if command == "approve" else InteractionKind.REVIEW_DECISION
        state.open_interaction(kind)
    elif command == "done":
        state.open_interaction(InteractionKind.GRILL)

    outcome = router.route(command, args, update_id=1)

    assert outcome.accepted is False
    assert commands.empty()
    if command in {"pause", "abort"}:
        assert state.control_state == ControlState.RUNNING


@pytest.mark.parametrize("args", [None, [], ["manual"], ["on", "off"], ["banana"]])
def test_gate_requires_exactly_on_or_off(args):
    commands = queue.Queue()
    outcome = CommandRouter(MissionState(), commands).route("gate", args, update_id=1)
    assert outcome.accepted is False
    assert commands.empty()


@pytest.mark.parametrize(
    ("args", "expected"),
    [(["on"], "manual"), (["off"], "auto")],
)
def test_gate_accepts_exact_public_syntax(args, expected):
    commands = queue.Queue()
    outcome = CommandRouter(MissionState(), commands).route("gate", args, update_id=1)
    assert outcome.accepted is True
    assert outcome.message == f"gate change accepted ({expected})"
    assert commands.get_nowait().get("mode") == expected


def test_telegram_cannot_answer_grill_before_question_delivery():
    state = MissionState()
    interaction = state.open_interaction(
        InteractionKind.GRILL,
        prompt="What should be implemented?",
    )
    commands = queue.Queue()
    router = CommandRouter(state, commands)

    outcome = router.route("answer", ["the API"], update_id=10, source="telegram")

    assert outcome.accepted is False
    assert "not been delivered" in outcome.message
    assert state.get_interaction().accepted_update_id is None
    assert commands.empty()

    assert state.mark_interaction_notified(interaction.id) is True
    outcome = router.route("answer", ["the API"], update_id=11, source="telegram")
    assert outcome.accepted is True
    assert commands.get_nowait().interaction_id == interaction.id


def test_stdin_can_answer_visible_grill_without_telegram_delivery():
    state = MissionState()
    state.open_interaction(InteractionKind.GRILL, prompt="Visible in terminal")
    commands = queue.Queue()
    outcome = CommandRouter(state, commands).route(
        "answer",
        ["terminal response"],
        update_id="stdin-1",
        source="stdin",
    )
    assert outcome.accepted is True


def test_only_first_interaction_response_is_reserved():
    state = MissionState()
    interaction = state.open_interaction(InteractionKind.APPROVAL)
    commands = queue.Queue()
    router = CommandRouter(state, commands)

    first = router.route("approve", [], update_id=20)
    second = router.route("reject", ["late"], update_id=21)

    assert first.accepted is True
    assert second.accepted is False
    assert "already" in second.message
    assert state.get_interaction().accepted_update_id == 20
    assert commands.qsize() == 1
    assert commands.get_nowait().interaction_id == interaction.id


def test_old_interaction_envelope_cannot_answer_new_interaction():
    state = MissionState()
    old = state.open_interaction(InteractionKind.APPROVAL)
    commands = queue.Queue()
    router = CommandRouter(state, commands)
    assert router.route("approve", [], update_id=1).accepted
    old_command = commands.get_nowait()
    state.close_interaction(old.id)
    current = state.open_interaction(InteractionKind.APPROVAL)

    assert current.id != old.id
    assert state.interaction_accepts(old_command.interaction_id, old_command.update_id) is False


@pytest.mark.parametrize(
    ("kind", "accepted", "rejected"),
    [
        (InteractionKind.GRILL, "done", "approve"),
        (InteractionKind.APPROVAL, "reject", "retry"),
        (InteractionKind.REVIEW_DECISION, "retry", "reject"),
    ],
)
def test_interaction_command_matrix(kind, accepted, rejected):
    state = MissionState()
    interaction = state.open_interaction(kind)
    if kind == InteractionKind.GRILL:
        state.mark_interaction_notified(interaction.id)
    commands = queue.Queue()
    router = CommandRouter(state, commands)

    invalid = router.route(rejected, [], update_id=1)
    valid = router.route(accepted, [], update_id=2)

    assert invalid.accepted is False
    assert valid.accepted is True


def test_checkpoint_discards_stale_decision_without_requeue(tmp_path, monkeypatch):
    monkeypatch.setattr("src.mission.signals.notify", lambda *_: None)
    state = MissionState()
    commands = queue.Queue()
    commands.put({"cmd": "approve", "update_id": 3, "interaction_id": "old"})

    assert check_signals(commands, tmp_path, state, BlockState()) is True
    assert commands.empty()


def test_resume_before_checkpoint_cancels_pending_pause(tmp_path, monkeypatch):
    monkeypatch.setattr("src.mission.signals.notify", lambda *_: None)
    state = MissionState()
    commands = queue.Queue()
    router = CommandRouter(state, commands)

    assert router.route("pause", [], update_id=1).accepted
    assert router.route("resume", [], update_id=2).accepted
    assert check_signals(commands, tmp_path, state, BlockState()) is True
    assert state.control_state == ControlState.RUNNING
    assert commands.empty()


def test_human_input_publishes_real_question_and_consumes_correlated_answer(tmp_path):
    state = MissionState()
    commands = queue.Queue()
    blocked = BlockState()
    human_input = HumanInput(
        commands,
        blocked,
        mission_state=state,
        harness=tmp_path,
    )
    result: list[str] = []
    worker = threading.Thread(target=lambda: result.append(human_input("Actual question?")))
    worker.start()

    deadline = time.monotonic() + 2
    while state.get_interaction() is None and time.monotonic() < deadline:
        time.sleep(0.01)
    interaction = state.get_interaction()
    assert interaction is not None
    assert interaction.prompt == "Actual question?"

    outcome = CommandRouter(state, commands).route(
        "answer",
        ["Actual answer"],
        update_id="stdin-1",
        source="stdin",
    )
    assert outcome.accepted
    worker.join(timeout=2)

    assert result == ["Actual answer"]
    assert state.get_interaction() is None
    assert blocked.reason is None


def test_human_input_abort_is_immediate_during_wait(tmp_path):
    state = MissionState()
    commands = queue.Queue()
    blocked = BlockState()
    human_input = HumanInput(
        commands,
        blocked,
        mission_state=state,
        harness=tmp_path,
    )
    result: list[str] = []
    worker = threading.Thread(target=lambda: result.append(human_input("Question?")))
    worker.start()

    deadline = time.monotonic() + 2
    while state.get_interaction() is None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert CommandRouter(state, commands).route("abort", [], update_id=8).accepted
    worker.join(timeout=2)

    assert result == [ABORT_SIGNAL]
    assert blocked.value == "user_abort"
    assert state.control_state == ControlState.ABORTED


def test_task_executor_checkpoints_after_each_phase(tmp_path):
    executor = object.__new__(TaskExecutor)
    executor.ctx = SimpleNamespace(harness=tmp_path, mode="full")
    executor.mission_state = MissionState()
    executor.command_queue = queue.Queue()
    executor.blocked = BlockState()
    executor.update_state = lambda *args, **kwargs: None
    executor.update_task = lambda *args, **kwargs: None
    executor.log = lambda *_: None
    phases: list[PhaseName] = []
    checkpoints: list[bool] = []
    executor._run_phase = lambda phase, *_: phases.append(phase)
    executor.check_signals = lambda *args: checkpoints.append(True) or True

    result = executor._run_task_phases(
        0,
        "T1",
        {"TASK_TITLE": "Task"},
        [PhaseName.SPEC, PhaseName.PLAN],
        1,
        0,
    )

    assert result is True
    assert phases == [PhaseName.SPEC, PhaseName.PLAN]
    assert len(checkpoints) == 2


def test_reimplement_checkpoint_observes_abort_after_llm_call(tmp_path, monkeypatch):
    monkeypatch.setattr("src.mission.signals.notify", lambda *_: None)
    state = MissionState()
    commands = queue.Queue()
    blocked = BlockState()
    phase_calls: list[str] = []
    ctx = SimpleNamespace(
        harness=tmp_path,
        get_task_complexity=lambda task: "M",
        get_task_pipeline_label=lambda task: "spec -> plan -> implement -> review",
        get_task_complexity_reason=lambda task: "test",
    )
    reviewer = HitlReviewer(
        ctx,
        SimpleNamespace(run=lambda config, variables, **kwargs: phase_calls.append(config.name)),
        commands,
        state,
        blocked,
        lambda *_: None,
        lambda **_: None,
    )
    assert CommandRouter(state, commands).route("abort", [], update_id=9).accepted

    assert reviewer.run_reimplement("T1", "Task", "") is False
    assert phase_calls == ["reimplement"]
    assert blocked.value == "user_abort"
    assert state.control_state == ControlState.ABORTED


def test_finalize_checkpoints_before_commit_after_report_and_before_merge(tmp_path, monkeypatch):
    state = MissionState()
    runner = object.__new__(MissionRunner)
    runner.ctx = SimpleNamespace(
        task="mission",
        branch="feature/test",
        harness=tmp_path,
        get_mission_pipeline=lambda: {"finalize": ["report", "merge"]},
    )
    runner.command_queue = queue.Queue()
    runner.mission_state = state
    runner.blocked = BlockState()
    runner.log = lambda *_: None
    runner._generate_report = lambda: None
    checkpoints: list[int] = []
    runner._checkpoint = lambda: checkpoints.append(len(checkpoints) + 1) or True
    (tmp_path / "tasks.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr("src.mission.runner.final_commit", lambda *_: None)
    monkeypatch.setattr("src.mission.runner.notify_result", lambda *_: None)
    monkeypatch.setattr("src.mission.runner.merge_to_develop", lambda *_: True)
    monkeypatch.setattr("src.mission.runner.notify", lambda *_: None)

    runner._run_finalize(0)

    assert checkpoints == [1, 2, 3, 4]
    assert state.control_state == ControlState.COMPLETED


def test_abort_during_report_is_not_marked_completed_without_merge(tmp_path, monkeypatch):
    state = MissionState()
    commands = queue.Queue()
    runner = object.__new__(MissionRunner)
    runner.ctx = SimpleNamespace(
        task="explore",
        branch="feature/test",
        harness=tmp_path,
        get_mission_pipeline=lambda: {"finalize": ["report"]},
    )
    runner.command_queue = commands
    runner.mission_state = state
    runner.blocked = BlockState()
    runner.log = lambda *_: None
    router = CommandRouter(state, commands)
    runner._generate_report = lambda: router.route("abort", [], update_id=44)
    monkeypatch.setattr("src.mission.runner.notify_result", lambda *_: None)
    monkeypatch.setattr("src.mission.signals.notify", lambda *_: None)

    runner._run_finalize(0)

    assert runner.blocked.value == "user_abort"
    assert state.control_state == ControlState.ABORTED
