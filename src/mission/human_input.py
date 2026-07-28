from __future__ import annotations

import queue
import sys
import threading
from pathlib import Path

from src.agent.loop import ABORT_SIGNAL, DONE_SIGNAL
from src.core.block_state import BlockKind, BlockReason
from src.core.state import ControlState, InteractionKind, MissionStateProtocol, _apply_gate_change
from src.mission.control import CommandRouter, coerce_envelope


def _handle_retry(line: str) -> dict:
    feedback = line[len("/retry"):].strip()
    return {"cmd": "retry", "feedback": feedback}


def _handle_reject(line: str) -> dict:
    reason = line[len("/reject"):].strip()
    return {"cmd": "reject", "reason": reason}


def _handle_answer(line: str) -> dict:
    text = line[len("/answer"):].strip()
    return {"cmd": "answer", "text": text}


def _handle_gate(line: str) -> dict:
    arg = line[len("/gate "):].strip() if line.startswith("/gate ") else ""
    if arg in ("on", "off"):
        return {"cmd": "gate", "mode": "manual" if arg == "on" else "auto"}
    return {"cmd": "gate", "text": arg}


def _handle_no_args(line: str) -> dict:
    command, _, remainder = line.partition(" ")
    result = {"cmd": command.lstrip("/")}
    if remainder.strip():
        result["text"] = remainder.strip()
    return result


_STDIN_COMMANDS = {
    "/approve": _handle_no_args,
    "/reject": _handle_reject,
    "/skip": _handle_no_args,
    "/abort": _handle_no_args,
    "/pause": _handle_no_args,
    "/resume": _handle_no_args,
    "/done": _handle_no_args,
    "/answer": _handle_answer,
    "/retry": _handle_retry,
    "/gate": _handle_gate,
}


def _parse_stdin_line(line: str) -> dict | None:
    line = line.strip()
    if not line:
        return None
    cmd = line.split()[0] if line.startswith("/") else None
    if cmd and cmd in _STDIN_COMMANDS:
        return _STDIN_COMMANDS[cmd](line)
    if cmd:
        return {"cmd": cmd.lstrip("/"), "text": line[len(cmd):].strip()}
    return {"cmd": "answer", "text": line}


def _stdin_reader(
    command_queue: queue.Queue,
    mission_state: MissionStateProtocol | None = None,
) -> None:
    router = CommandRouter(mission_state, command_queue) if mission_state else None
    while True:
        try:
            line = input()
        except EOFError:
            break
        parsed = _parse_stdin_line(line)
        if not parsed:
            continue
        if router is None:
            # Compatibility for embedders which have not supplied state.  The
            # production CLI supplies state and therefore always uses routing.
            command_queue.put(parsed)
            continue
        outcome = router.route_legacy(parsed, source="stdin")
        if not outcome.accepted:
            print(f"Control command rejected: {outcome.message}", flush=True)


def _start_stdin_listener(
    command_queue: queue.Queue,
    mission_state: MissionStateProtocol | None = None,
) -> None:
    if not sys.stdin.isatty():
        return
    thread = threading.Thread(
        target=_stdin_reader,
        args=(command_queue, mission_state),
        daemon=True,
        name="harness-stdin-control",
    )
    thread.start()


class HumanInput:

    def __init__(
        self,
        command_queue,
        blocked,
        log=None,
        *,
        mission_state: MissionStateProtocol | None = None,
        harness: Path | None = None,
    ):
        self.command_queue = command_queue
        self.blocked = blocked
        self.log = log
        self.mission_state = mission_state
        self.harness = harness

    def __call__(self, question_text):
        print(f"\n{'='*60}")
        print(question_text)
        print(f"{'='*60}")
        print("[Responde aqui o desde Telegram con /answer. /done para terminar]", flush=True)

        interaction = None
        if self.mission_state is not None:
            interaction = self.mission_state.open_interaction(
                InteractionKind.GRILL,
                task_id=self.mission_state.task_id,
                prompt=question_text,
            )
        try:
            while True:
                if (
                    self.mission_state is not None
                    and self.mission_state.control_state in {
                        ControlState.ABORT_PENDING,
                        ControlState.ABORTED,
                    }
                ):
                    self._abort()
                    return ABORT_SIGNAL
                try:
                    raw = self.command_queue.get(timeout=5)
                except queue.Empty:
                    continue
                cmd = coerce_envelope(raw)
                action = cmd.name
                if action == "abort":
                    self._abort()
                    return ABORT_SIGNAL
                if action == "gate" and self.harness is not None and cmd.get("mode") in {"manual", "auto"}:
                    _apply_gate_change(cmd["mode"], self.harness, self.mission_state)
                    continue
                if action not in {"answer", "done"}:
                    continue
                if interaction is not None and not self.mission_state.interaction_accepts(
                    cmd.interaction_id,
                    cmd.update_id,
                ):
                    continue
                if action == "answer":
                    text = cmd.get("text", "")
                    if self.log:
                        self.log(f"  < User: {text[:80]}")
                    return text
                if self.log:
                    self.log("  < User: /done")
                return DONE_SIGNAL
        finally:
            if interaction is not None:
                self.mission_state.close_interaction(interaction.id)

    def _abort(self) -> None:
        self.blocked.reason = BlockReason(BlockKind.USER_ABORT)
        if self.mission_state is not None:
            self.mission_state.set_control_state(ControlState.ABORTED)
