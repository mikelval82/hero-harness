from __future__ import annotations

import json
import threading

from mission_orchestrator.domain.session import MissionSession
from mission_orchestrator.ports.artifacts import ArtifactStore
from mission_orchestrator.ports.session_store import SessionConflictError


class FilesystemMissionSessionStore:
    def __init__(self, artifacts: ArtifactStore, artifact_name: str = "_session.json") -> None:
        self.artifacts = artifacts
        self.artifact_name = artifact_name
        self._lock = threading.Lock()

    def load(self, mission_id: str) -> MissionSession:
        raw = self.artifacts.read_text(self.artifact_name, default="")
        if not raw:
            return MissionSession(mission_id)
        session = MissionSession.from_json(json.loads(raw))
        if session.mission_id != mission_id:
            raise ValueError(
                f"session belongs to {session.mission_id!r}, not requested mission {mission_id!r}"
            )
        return session

    def save(self, session: MissionSession, *, expected_revision: int) -> None:
        with self._lock:
            current = self.load(session.mission_id)
            if current.revision != expected_revision:
                raise SessionConflictError(current.revision)
            if session.revision != expected_revision + 1:
                raise ValueError(
                    "saved session revision must be exactly one greater than expected_revision"
                )
            payload = json.dumps(session.to_json(), indent=2, ensure_ascii=False) + "\n"
            self.artifacts.write_text(self.artifact_name, payload)