from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from mission_orchestrator.adapters.filesystem.artifact_store import FilesystemArtifactStore
from mission_orchestrator.application.burst_executor import BurstExecutor
from mission_orchestrator.domain.phase import PhaseName
from mission_orchestrator.domain.task import Task, TaskComplexity


class RecordingPhaseExecutor:
    def __init__(self, root: Path) -> None:
        self.services = SimpleNamespace(artifacts=FilesystemArtifactStore(root))
        self.calls: list[tuple[PhaseName, dict]] = []

    def run(self, phase: PhaseName, **kwargs):  # noqa: ANN003, ANN201
        self.calls.append((phase, kwargs))
        return SimpleNamespace(block=None)


class BurstExecutorTest(unittest.TestCase):
    def test_fallback_implementation_propagates_task_complexity(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            phases = RecordingPhaseExecutor(Path(raw))

            block = BurstExecutor(phases).run(
                Task("T-1", "Complex implementation", complexity=TaskComplexity.L)
            )

            self.assertIsNone(block)
            self.assertEqual(phases.calls[0][0], PhaseName.IMPLEMENT)
            self.assertEqual(phases.calls[0][1]["complexity"], "L")


if __name__ == "__main__":
    unittest.main()
