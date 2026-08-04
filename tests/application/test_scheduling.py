"""Acceptance tests for K8 - dependency-aware scheduling and blocked status.

Spec: docs/hero-v2/specs/K8-scheduling.md (D1-D5; D6 is the pre-existing
orchestrator suite staying green).
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from mission_orchestrator.adapters.filesystem.artifact_store import FilesystemArtifactStore
from mission_orchestrator.application.orchestrator import MissionOrchestrator
from mission_orchestrator.domain.mission import MissionMode
from mission_orchestrator.domain.result import MissionOutcome
from mission_orchestrator.domain.task import Task, TaskStatus, summarize_tasks
from mission_orchestrator.domain.workplan import dependency_block_reason, next_runnable_index

from tests.application.test_orchestrator import FakeAgent, make_services


def _task(task_id: str, status: TaskStatus = TaskStatus.PENDING, deps: list[str] | None = None) -> Task:
    return Task(id=task_id, title=task_id, status=status, dependencies=deps or [])


class BlockedStatusTest(unittest.TestCase):
    def test_d1_blocked_parses_and_roundtrips(self) -> None:
        self.assertIs(TaskStatus.parse("blocked"), TaskStatus.BLOCKED)
        task = _task("T-1", status=TaskStatus.BLOCKED)
        task.failure_reason = "dependency failed: T-0"
        loaded = Task.from_json(task.to_json())
        self.assertIs(loaded.status, TaskStatus.BLOCKED)
        self.assertEqual(loaded.failure_reason, "dependency failed: T-0")


class SchedulingFunctionsTest(unittest.TestCase):
    def test_d2_next_runnable_respects_dependencies(self) -> None:
        tasks = [_task("T-2", deps=["T-1"]), _task("T-1")]
        self.assertEqual(next_runnable_index(tasks), 1)
        tasks[1].status = TaskStatus.COMPLETED
        self.assertEqual(next_runnable_index(tasks), 0)
        tasks[0].status = TaskStatus.COMPLETED
        self.assertIsNone(next_runnable_index(tasks))

    def test_d2_no_runnable_when_dependency_failed(self) -> None:
        tasks = [_task("T-1", status=TaskStatus.FAILED), _task("T-2", deps=["T-1"])]
        self.assertIsNone(next_runnable_index(tasks))

    def test_d3_dependency_block_reason(self) -> None:
        by_id = {
            "T-1": _task("T-1", status=TaskStatus.FAILED),
            "T-2": _task("T-2", status=TaskStatus.BLOCKED),
            "T-3": _task("T-3", status=TaskStatus.COMPLETED),
        }
        self.assertEqual(dependency_block_reason(_task("A", deps=["T-1"]), by_id), "dependency failed: T-1")
        self.assertEqual(dependency_block_reason(_task("B", deps=["T-2"]), by_id), "dependency blocked: T-2")
        self.assertIsNone(dependency_block_reason(_task("C", deps=["T-3"]), by_id))

    def test_d4_summary_reports_blocked(self) -> None:
        blocked = _task("T-2", status=TaskStatus.BLOCKED)
        blocked.failure_reason = "dependency failed: T-1"
        summary = summarize_tasks([_task("T-1", status=TaskStatus.FAILED), blocked])
        self.assertIn("Blocked: 1", summary)
        self.assertIn("BLOCKED [T-2]: dependency failed: T-1", summary)


class SchedulingMissionTest(unittest.TestCase):
    def test_d5_failed_dependency_blocks_dependent_and_runs_independent(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            agent = FakeAgent(FilesystemArtifactStore(tmp / "harness"), fail_first_implement=True)
            services, context, git = make_services(tmp, MissionMode.HOTFIX, agent=agent)
            agent.artifacts = services.artifacts
            services.tasks.save(
                [
                    _task("T-1"),
                    _task("T-2", deps=["T-1"]),
                    _task("T-3"),
                ]
            )
            result = MissionOrchestrator(services, context).run()
            self.assertEqual(result.outcome, MissionOutcome.PARTIAL)
            by_id = {task["id"]: task for task in json.loads(services.artifacts.read_text("tasks.json"))}
            self.assertEqual(by_id["T-1"]["status"], "failed")
            self.assertEqual(by_id["T-2"]["status"], "blocked")
            self.assertIn("T-1", by_id["T-2"]["failure_reason"])
            self.assertEqual(by_id["T-3"]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
