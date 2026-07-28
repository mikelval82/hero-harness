from __future__ import annotations

import queue
import threading
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from src.core.state import ControlState, InteractionKind, MissionStateProtocol


READ_ONLY_COMMANDS = frozenset(
    {
        "help",
        "start",
        "status",
        "log",
        "verbose",
        "brief",
        "brainstorm",
        "tasks",
        "spec",
        "plan",
        "decisions",
        "audit",
        "report",
        "ask",
    }
)
CONTROL_COMMANDS = frozenset({"pause", "resume", "abort", "gate"})
INTERACTION_COMMANDS = frozenset(
    {"answer", "done", "approve", "reject", "retry", "skip"}
)
_NO_ARGUMENT_COMMANDS = frozenset(
    {"pause", "resume", "abort", "approve", "skip", "done"}
)

_INTERACTION_COMMANDS: dict[InteractionKind, frozenset[str]] = {
    InteractionKind.GRILL: frozenset({"answer", "done"}),
    InteractionKind.APPROVAL: frozenset({"approve", "reject"}),
    InteractionKind.REVIEW_DECISION: frozenset({"retry", "skip", "approve"}),
}
_MUTATION_REJECTING_STATES = {
    ControlState.ABORT_PENDING,
    ControlState.ABORTED,
    ControlState.COMPLETED,
    ControlState.FAILED,
}


@dataclass(frozen=True)
class CommandEnvelope:
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    update_id: int | str | None = None
    interaction_id: str | None = None
    source: str = "internal"

    @property
    def cmd(self) -> str:
        return self.name

    def get(self, key: str, default=None):
        if key == "cmd":
            return self.name
        if key == "update_id":
            return self.update_id
        if key == "interaction_id":
            return self.interaction_id
        if key == "source":
            return self.source
        return self.args.get(key, default)

    def __getitem__(self, key: str):
        sentinel = object()
        value = self.get(key, sentinel)
        if value is sentinel:
            raise KeyError(key)
        return value

    def as_dict(self) -> dict[str, Any]:
        return {
            "cmd": self.name,
            **self.args,
            "update_id": self.update_id,
            "interaction_id": self.interaction_id,
            "source": self.source,
        }


@dataclass(frozen=True)
class CommandOutcome:
    accepted: bool
    message: str
    envelope: CommandEnvelope | None = None
    queued: bool = False


def coerce_envelope(value: CommandEnvelope | Mapping[str, Any]) -> CommandEnvelope:
    if isinstance(value, CommandEnvelope):
        return value
    name = str(value.get("cmd", "")).lower().lstrip("/")
    metadata = {"cmd", "update_id", "interaction_id", "source"}
    return CommandEnvelope(
        name=name,
        args={key: item for key, item in value.items() if key not in metadata},
        update_id=value.get("update_id"),
        interaction_id=value.get("interaction_id"),
        source=str(value.get("source", "legacy")),
    )


class CommandRouter:
    """Validate and correlate commands before they reach mission consumers."""

    def __init__(
        self,
        mission_state: MissionStateProtocol,
        command_queue: queue.Queue,
    ) -> None:
        self.state = mission_state
        self.command_queue = command_queue
        self._counter = 0
        self._counter_lock = threading.Lock()

    def route(
        self,
        name: str,
        args: Mapping[str, Any] | list[str] | tuple[str, ...] | str | None = None,
        *,
        update_id: int | str | None = None,
        source: str = "telegram",
    ) -> CommandOutcome:
        command = name.lower().strip().lstrip("/").split("@", 1)[0]
        normalized_args = _normalize_args(command, args)
        if update_id is None:
            update_id = self._local_update_id(source)

        if command in READ_ONLY_COMMANDS:
            envelope = CommandEnvelope(command, normalized_args, update_id, source=source)
            return CommandOutcome(True, "read command accepted", envelope, False)

        if command not in CONTROL_COMMANDS | INTERACTION_COMMANDS:
            return CommandOutcome(False, f"unknown command: /{command or '?'}")

        argument_error = _validate_command_args(command, args, normalized_args)
        if argument_error:
            return CommandOutcome(False, argument_error)

        snapshot = self.state.snapshot()
        control = ControlState(snapshot["control_state"])
        if control in _MUTATION_REJECTING_STATES:
            return CommandOutcome(False, f"mission is {control.value}")

        interaction = self.state.get_interaction()
        if interaction is not None and command in {"pause", "resume"}:
            return CommandOutcome(
                False,
                f"/{command} is not valid during {interaction.kind.value}",
            )

        if command == "gate":
            mode = normalized_args.get("mode")
            envelope = CommandEnvelope(command, normalized_args, update_id, source=source)
            return self._accept(envelope, f"gate change accepted ({mode})")

        if command == "abort":
            if not self.state.request_abort():
                return CommandOutcome(False, "abort has already been requested")
            envelope = CommandEnvelope(command, normalized_args, update_id, source=source)
            return self._accept(envelope, "abort requested")

        if command == "pause":
            if not self.state.request_pause():
                return CommandOutcome(False, "pause is only valid while the mission is running")
            envelope = CommandEnvelope(command, normalized_args, update_id, source=source)
            return self._accept(envelope, "pause requested")

        if command == "resume":
            if not self.state.request_resume():
                return CommandOutcome(False, "mission is not paused")
            envelope = CommandEnvelope(command, normalized_args, update_id, source=source)
            return self._accept(envelope, "resume accepted")

        if interaction is None:
            return CommandOutcome(False, f"/{command} is not valid without an active interaction")
        if command not in _INTERACTION_COMMANDS[interaction.kind]:
            return CommandOutcome(
                False,
                f"/{command} is not valid during {interaction.kind.value}",
            )
        if (
            source == "telegram"
            and interaction.kind == InteractionKind.GRILL
            and not interaction.notified
        ):
            return CommandOutcome(False, "the current question has not been delivered yet")

        reservation = self.state.reserve_interaction(interaction.id, update_id)
        if reservation == "already_accepted":
            return CommandOutcome(False, "this interaction already has an accepted response")
        if reservation != "accepted":
            return CommandOutcome(False, "this interaction is no longer active")

        envelope = CommandEnvelope(
            command,
            normalized_args,
            update_id,
            interaction_id=interaction.id,
            source=source,
        )
        if interaction.kind == InteractionKind.REVIEW_DECISION and command == "approve":
            message = "force-approval accepted"
        elif command == "pause":
            message = "pause requested"
        else:
            message = f"{command} accepted"
        return self._accept(envelope, message)

    def route_legacy(
        self,
        command: Mapping[str, Any],
        *,
        source: str = "stdin",
    ) -> CommandOutcome:
        name = str(command.get("cmd", ""))
        args = {key: value for key, value in command.items() if key != "cmd"}
        return self.route(name, args, source=source)

    def _accept(
        self,
        envelope: CommandEnvelope,
        message: str,
    ) -> CommandOutcome:
        self.command_queue.put(envelope)
        return CommandOutcome(True, message, envelope, True)

    def _local_update_id(self, source: str) -> str:
        with self._counter_lock:
            self._counter += 1
            counter = self._counter
        return f"{source}:{counter}:{uuid.uuid4().hex}"


def _normalize_args(
    command: str,
    args: Mapping[str, Any] | list[str] | tuple[str, ...] | str | None,
) -> dict[str, Any]:
    if command in _NO_ARGUMENT_COMMANDS:
        return {}
    if isinstance(args, Mapping):
        result = dict(args)
    elif isinstance(args, str):
        result = {"text": args.strip()}
    else:
        words = [str(item) for item in (args or ())]
        result = {"text": " ".join(words).strip()}

    text = str(result.get("text", "")).strip()
    if command == "answer":
        result["text"] = str(result.get("text", text)).strip()
    elif command == "reject":
        result["reason"] = str(result.get("reason", text)).strip()
        result.pop("text", None)
    elif command == "retry":
        result["feedback"] = str(result.get("feedback", text)).strip()
        result.pop("text", None)
    elif command == "gate":
        raw = str(result.get("mode", text)).strip().lower()
        result = {"mode": {"on": "manual", "off": "auto"}.get(raw, raw)}
    return result


def _validate_command_args(
    command: str,
    raw_args: Mapping[str, Any] | list[str] | tuple[str, ...] | str | None,
    normalized: Mapping[str, Any],
) -> str:
    if command in _NO_ARGUMENT_COMMANDS and _contains_args(raw_args):
        return f"/{command} does not accept arguments"
    if command == "gate" and not _valid_gate_args(raw_args):
        return "usage: /gate on|off"
    if command == "answer" and not str(normalized.get("text", "")).strip():
        return "usage: /answer <text>"
    if command == "answer" and isinstance(raw_args, Mapping) and set(raw_args) != {"text"}:
        return "usage: /answer <text>"
    if command == "reject" and isinstance(raw_args, Mapping) and not set(raw_args) <= {"reason", "text"}:
        return "usage: /reject [reason]"
    if command == "retry" and isinstance(raw_args, Mapping) and not set(raw_args) <= {"feedback", "text"}:
        return "usage: /retry [feedback]"
    return ""


def _contains_args(
    args: Mapping[str, Any] | list[str] | tuple[str, ...] | str | None,
) -> bool:
    if args is None:
        return False
    if isinstance(args, Mapping):
        return any(str(value).strip() for value in args.values()) or bool(args)
    if isinstance(args, str):
        return bool(args.strip())
    return bool(args)


def _valid_gate_args(
    args: Mapping[str, Any] | list[str] | tuple[str, ...] | str | None,
) -> bool:
    if isinstance(args, Mapping):
        if set(args) not in ({"mode"}, {"text"}):
            return False
        value = args.get("mode", args.get("text", ""))
        # ``manual``/``auto`` are the normalized values emitted by the stdin
        # parser; public Telegram syntax remains strictly on/off.
        return str(value).strip().lower() in {"on", "off", "manual", "auto"}
    if isinstance(args, str):
        return args.strip().lower() in {"on", "off"}
    values = list(args or ())
    return len(values) == 1 and str(values[0]).strip().lower() in {"on", "off"}
