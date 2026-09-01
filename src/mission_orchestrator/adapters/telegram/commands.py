from __future__ import annotations

from dataclasses import dataclass

from mission_orchestrator.domain.command import Command, parse_control_command


STATUS_COMMANDS = {
    "status",
    "log",
    "verbose",
    "missions",
    "help",
    "brief",
    "plan",
    "decisions",
    "spec",
    "audit",
    "statusfile",
    "brainstorm",
    "tasks",
    "hot",
    "warm",
    "ask",
}
ARTIFACTS = {
    "brief": "brief.md",
    "plan": "plan.md",
    "decisions": "decisions.md",
    "spec": "spec.md",
    "audit": "audit.md",
    "statusfile": "status.md",
    "brainstorm": "brainstorm.md",
    "tasks": "tasks.json",
    "hot": "context-hot.md",
    "warm": "context-cold.md",
}


@dataclass(frozen=True)
class TelegramCommand:
    name: str
    rest: str = ""
    target: str = ""
    bus_command: Command | None = None


def parse_telegram_command(text: str) -> TelegramCommand | None:
    raw = text.strip()
    if not raw.startswith("/"):
        return None
    first, _, rest = raw.partition(" ")
    name = first[1:]
    target = ""
    if "@" in name:
        name, target = name.split("@", 1)
    elif rest.startswith("@"):
        maybe_target, _, remainder = rest.partition(" ")
        target = maybe_target[1:]
        rest = remainder
    name = name.lower()
    normalized = f"/{name} {rest}".strip()
    bus = parse_control_command(normalized)
    return TelegramCommand(name=name, rest=rest.strip(), target=target, bus_command=bus)

