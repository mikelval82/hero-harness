from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from mission_orchestrator.adapters.filesystem.artifact_store import FilesystemArtifactStore
from mission_orchestrator.application.design_realization import DesignRealizationStore


class DesignRealizationStoreTest(unittest.TestCase):
    def test_records_accepted_task_by_node_and_relationship(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            store = DesignRealizationStore(FilesystemArtifactStore(Path(raw)))
            entry = store.record(
                task_id="T-2",
                contract={
                    "snapshot_id": "snap-7",
                    "task": {"title": "Connect notifier", "covers": ["connect:notifier"]},
                    "nodes": [{"id": "notifier"}, {"id": "service"}],
                    "relationships": [{"source": "service", "target": "notifier", "relation": "uses"}],
                },
                commit="abc123",
                observed_revision=9,
                accepted=True,
            )

            view = store.view()

            self.assertEqual(entry["status"], "accepted")
            self.assertEqual(view["nodes"]["notifier"]["commit"], "abc123")
            self.assertEqual(view["edges"]["service|notifier|uses"]["task_id"], "T-2")
            self.assertEqual(view["tasks"]["T-2"]["observed_revision"], 9)
            self.assertEqual(json.loads(store.artifacts.read_text("design-realization.json"))["schema_version"], 1)


if __name__ == "__main__":
    unittest.main()
