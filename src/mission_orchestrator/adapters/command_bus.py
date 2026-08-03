from __future__ import annotations

import queue
from collections.abc import Iterable

from mission_orchestrator.domain.command import Command


class QueueCommandBus:
    def __init__(self) -> None:
        self._queue: queue.Queue[Command] = queue.Queue()
        self._deferred: list[Command] = []

    def publish(self, command: Command) -> None:
        self._queue.put(command)

    def get_nowait(self) -> Command | None:
        if self._deferred:
            return self._deferred.pop(0)
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    def get(self, timeout_seconds: float) -> Command | None:
        if self._deferred:
            return self._deferred.pop(0)
        try:
            return self._queue.get(timeout=timeout_seconds)
        except queue.Empty:
            return None

    def defer(self, commands: Iterable[Command]) -> None:
        self._deferred = list(commands) + self._deferred

