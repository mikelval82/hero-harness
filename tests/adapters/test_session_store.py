from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mission_orchestrator.adapters.filesystem.artifact_store import FilesystemArtifactStore
from mission_orchestrator.adapters.filesystem.session_store import FilesystemMissionSessionStore
from mission_orchestrator.domain.session import MissionStage
from mission_orchestrator.ports.session_store import SessionConflictError


class MissionSessionStoreTest(unittest.TestCase):
    def test_save_uses_compare_and_swap(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as raw:
            artifacts = FilesystemArtifactStore(Path(raw))
            store = FilesystemMissionSessionStore(artifacts)
            draft = store.load("mission-1")
            researching = draft.move_to(MissionStage.RESEARCHING, active_phase="research")

            store.save(researching, expected_revision=0)

            self.assertEqual(store.load("mission-1"), researching)
            with self.assertRaisesRegex(SessionConflictError, "current revision is 1"):
                store.save(researching, expected_revision=0)


if __name__ == "__main__":
    unittest.main()