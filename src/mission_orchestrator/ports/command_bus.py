from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from mission_orchestrator.domain.command import Command


class CommandBus(Protocol):
    def publish(self, command: Command) -> None: ...
    def get_nowait(self) -> Command | None: ...
    def get(self, timeout_seconds: float) -> Command | None: ...
    def defer(self, commands: Iterable[Command]) -> None: ...

