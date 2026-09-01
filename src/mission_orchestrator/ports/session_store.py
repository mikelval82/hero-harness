from __future__ import annotations

from typing import Protocol

from mission_orchestrator.domain.session import MissionSession


class SessionConflictError(RuntimeError):
    def __init__(self, current_revision: int) -> None:
        super().__init__(f"session revision conflict; current revision is {current_revision}")
        self.current_revision = current_revision


class MissionSessionStore(Protocol):
    def load(self, mission_id: str) -> MissionSession: ...
    def save(self, session: MissionSession, *, expected_revision: int) -> None: ...