from __future__ import annotations

import queue
import sys
import threading

from src.agent.loop import DONE_SIGNAL
from src.core.block_state import BlockKind, BlockReason


def _handle_retry(line: str) -> dict:
    feedback = line[len("/retry"):].strip()
    return {"cmd": "retry", "feedback": feedback}


def _handle_gate(line: str) -> dict | None:
    arg = line[len("/gate "):].strip() if line.startswith("/gate ") else ""
    if arg in ("on", "off"):
        return {"cmd": "gate", "mode": "manual" if arg == "on" else "auto"}
    return None


_STDIN_COMMANDS = {
    "/approve": lambda _: {"cmd": "approve"},
    "/skip": lambda _: {"cmd": "skip"},
    "/abort": lambda _: {"cmd": "abort"},
    "/pause": lambda _: {"cmd": "pause"},
    "/resume": lambda _: {"cmd": "resume"},
    "/done": lambda _: {"cmd": "done"},
    "/retry": _handle_retry,
    "/gate": _handle_gate,
}


def _parse_stdin_line(line: str) -> dict:
    line = line.strip()
    if not line:
        return None
    if line in _STDIN_COMMANDS:
        return _STDIN_COMMANDS[line](line)
    cmd = line.split()[0] if line.startswith("/") else None
    if cmd and cmd in _STDIN_COMMANDS:
        result = _STDIN_COMMANDS[cmd](line)
        if result is not None:
            return result
    return {"cmd": "answer", "text": line}


def _stdin_reader(command_queue: queue.Queue) -> None:
    while True:
        try:
            line = input()
        except EOFError:
            break
        parsed = _parse_stdin_line(line)
        if parsed:
            command_queue.put(parsed)


def _start_stdin_listener(command_queue: queue.Queue) -> None:
    if not sys.stdin.isatty():
        return
    t = threading.Thread(target=_stdin_reader, args=(command_queue,), daemon=True)
    t.start()


class HumanInput:

    def __init__(self, command_queue, blocked, log=None):
        self.command_queue = command_queue
        self.blocked = blocked
        self.log = log

    def _restore_deferred(self, deferred):
        for cmd in deferred:
            self.command_queue.put(cmd)

    def __call__(self, question_text):
        print(f"\n{'='*60}")
        print(question_text)
        print(f"{'='*60}")
        print("[Responde aqui o desde Telegram con /answer. /done para terminar]", flush=True)
        deferred = []
        try:
            while True:
                try:
                    cmd = self.command_queue.get(timeout=5)
                except queue.Empty:
                    continue
                action = cmd.get("cmd", "")
                if action == "answer":
                    text = cmd.get("text", "")
                    if self.log:
                        self.log(f"  < User: {text[:80]}")
                    return text
                if action == "done":
                    if self.log:
                        self.log("  < User: /done")
                    return DONE_SIGNAL
                if action == "abort":
                    self.blocked.reason = BlockReason(BlockKind.USER_ABORT)
                    return DONE_SIGNAL
                deferred.append(cmd)
        finally:
            self._restore_deferred(deferred)
