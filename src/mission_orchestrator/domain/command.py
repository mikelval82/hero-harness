from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from mission_orchestrator.domain.mission import GateMode


class CommandKind(Enum):
    ABORT = "abort"
    PAUSE = "pause"
    RESUME = "resume"
    APPROVE = "approve"
    REJECT = "reject"
    RETRY = "retry"
    SKIP = "skip"
    GATE = "gate"
    ANSWER = "answer"
    DONE = "done"


@dataclass(frozen=True)
class Command:
    kind: CommandKind
    text: str = ""
    reason: str = ""
    feedback: str = ""
    gate_mode: GateMode | None = None


def parse_control_command(text: str) -> Command | None:
    raw = text.strip()
    if not raw:
        return None
    if not raw.startswith("/"):
        return Command(CommandKind.ANSWER, text=raw)
    command, _, rest = raw[1:].partition(" ")
    command = command.lower()
    rest = rest.strip()
    if command == "abort":
        return Command(CommandKind.ABORT, reason=rest)
    if command == "pause":
        return Command(CommandKind.PAUSE)
    if command == "resume":
        return Command(CommandKind.RESUME)
    if command == "approve":
        return Command(CommandKind.APPROVE)
    if command == "reject":
        return Command(CommandKind.REJECT, reason=rest)
    if command == "retry":
        return Command(CommandKind.RETRY, feedback=rest)
    if command == "skip":
        return Command(CommandKind.SKIP, reason=rest)
    if command == "answer":
        return Command(CommandKind.ANSWER, text=rest)
    if command == "done":
        return Command(CommandKind.DONE)
    if command == "gate":
        lowered = rest.lower()
        if lowered in {"on", "manual", "true", "1"}:
            return Command(CommandKind.GATE, gate_mode=GateMode.MANUAL)
        if lowered in {"off", "auto", "false", "0"}:
            return Command(CommandKind.GATE, gate_mode=GateMode.AUTO)
    return None

