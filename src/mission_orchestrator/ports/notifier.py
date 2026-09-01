from __future__ import annotations

from typing import Protocol

from mission_orchestrator.domain.result import MissionResult


class Notifier(Protocol):
    def notify(self, message: str) -> None: ...
    def notify_result(self, result: MissionResult) -> None: ...

