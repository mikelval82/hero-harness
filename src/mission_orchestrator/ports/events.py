from __future__ import annotations

from typing import Protocol

from mission_orchestrator.domain.event import MissionEvent


class EventPublisher(Protocol):
    def publish(self, kind: str, payload: dict) -> None: ...
    def events_since(self, after_id: int, limit: int = 200) -> list[MissionEvent]: ...
