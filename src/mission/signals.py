from __future__ import annotations

import queue

from src.core.block_state import BlockKind, BlockReason
from src.core.notification import notify
from src.core.state import _apply_gate_change


def _restore_deferred(command_queue, deferred):
    for cmd in deferred:
        command_queue.put(cmd)


def _wait_for_resume(command_queue, harness, mission_state, blocked, deferred):
    while True:
        try:
            cmd = command_queue.get(timeout=5)
        except queue.Empty:
            continue
        action = cmd.get("cmd", "")
        if action == "resume":
            return True
        if action == "abort":
            blocked.reason = BlockReason(BlockKind.USER_ABORT)
            notify("\U0001f6d1 Mission aborted by user via Telegram")
            return False
        if action == "gate":
            _apply_gate_change(cmd["mode"], harness, mission_state)
        else:
            deferred.append(cmd)


def check_signals(command_queue, harness, mission_state, blocked):
    deferred = []
    try:
        while True:
            try:
                cmd = command_queue.get_nowait()
            except queue.Empty:
                break
            action = cmd.get("cmd", "")
            if action == "abort":
                blocked.reason = BlockReason(BlockKind.USER_ABORT)
                notify("\U0001f6d1 Mission aborted by user via Telegram")
                return False
            if action == "pause":
                if not _wait_for_resume(command_queue, harness, mission_state, blocked, deferred):
                    return False
            elif action == "gate":
                _apply_gate_change(cmd["mode"], harness, mission_state)
            else:
                deferred.append(cmd)
        return True
    finally:
        _restore_deferred(command_queue, deferred)
