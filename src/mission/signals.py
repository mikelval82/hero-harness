from __future__ import annotations

import queue

from src.core.block_state import BlockKind, BlockReason
from src.core.notification import notify
from src.core.state import ControlState, MissionStateProtocol, _apply_gate_change
from src.mission.control import coerce_envelope


def _abort(mission_state: MissionStateProtocol | None, blocked) -> bool:
    blocked.reason = BlockReason(BlockKind.USER_ABORT)
    if mission_state is not None:
        mission_state.set_control_state(ControlState.ABORTED)
    notify("\U0001f6d1 Mission aborted by user")
    return False


def _wait_for_resume(command_queue, harness, mission_state, blocked):
    if (
        mission_state is not None
        and mission_state.control_state == ControlState.RUNNING
    ):
        # A /resume received before this checkpoint cancelled pause_pending.
        return True

    if mission_state is not None:
        mission_state.set_control_state(ControlState.PAUSED)

    while True:
        if (
            mission_state is not None
            and mission_state.control_state == ControlState.ABORT_PENDING
        ):
            return _abort(mission_state, blocked)
        try:
            raw = command_queue.get(timeout=5)
        except queue.Empty:
            continue
        cmd = coerce_envelope(raw)
        if cmd.name == "resume":
            if mission_state is not None:
                mission_state.set_control_state(ControlState.RUNNING)
            return True
        if cmd.name == "abort":
            return _abort(mission_state, blocked)
        if cmd.name == "gate" and cmd.get("mode") in {"manual", "auto"}:
            _apply_gate_change(cmd["mode"], harness, mission_state)
        # Commands that cannot be acted on in a pause are intentionally
        # discarded.  Requeueing would let stale decisions escape into a
        # later interaction.


def check_signals(command_queue, harness, mission_state, blocked):
    """Apply control commands at a safe checkpoint.

    Commands for an interaction are consumed only by that interaction.  If
    they reach a checkpoint they are stale and are discarded, never deferred.
    """
    if (
        mission_state is not None
        and mission_state.control_state == ControlState.ABORT_PENDING
    ):
        return _abort(mission_state, blocked)
    if (
        mission_state is not None
        and mission_state.control_state in {
            ControlState.PAUSE_PENDING,
            ControlState.PAUSED,
        }
    ):
        return _wait_for_resume(command_queue, harness, mission_state, blocked)

    while True:
        try:
            raw = command_queue.get_nowait()
        except queue.Empty:
            break
        cmd = coerce_envelope(raw)
        if cmd.name == "abort":
            return _abort(mission_state, blocked)
        if cmd.name == "pause":
            if mission_state is not None:
                # A resume may have cancelled the pending pause while the
                # phase was still running.
                if (
                    mission_state.control_state == ControlState.RUNNING
                    and cmd.source != "legacy"
                ):
                    continue
                mission_state.set_control_state(ControlState.PAUSE_PENDING)
            if not _wait_for_resume(command_queue, harness, mission_state, blocked):
                return False
        elif cmd.name == "gate" and cmd.get("mode") in {"manual", "auto"}:
            _apply_gate_change(cmd["mode"], harness, mission_state)
        # resume outside a pause and every interaction command are stale here.

    return True


def control_checkpoint(command_queue, harness, mission_state, blocked) -> bool:
    """Named wrapper used at phase and git boundaries."""
    return check_signals(command_queue, harness, mission_state, blocked)
