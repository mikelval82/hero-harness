from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MissionEvent:
    event_id: int
    timestamp: str
    mission: str
    kind: str
    payload: dict
    task_id: str | None = None
    snapshot_id: str | None = None
