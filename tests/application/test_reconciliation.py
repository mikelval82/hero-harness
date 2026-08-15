"""Acceptance tests for K9 - reconciliation and merge gate.

Spec: docs/hero-v2/specs/K9-reconciliation-gate.md (D1-D7; D8 is the
pre-existing suite: missions without changeset merge as before).
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
from mission_orchestrator.domain.reconciliation import (
    OperationState,
    Reconciliation,
    merge_gate_reasons,
    reconcile,
)
from mission_orchestrator.domain.result import MissionOutcome
from mission_orchestrator.domain.task import Task, TaskStatus

from tests.application.test_orchestrator import FakeAgent, make_services


def _op(op_id: str, kind: str, locator: str | None = None) -> dict:
    return {
        "id": op_id,
        "kind": kind,
        "target_node": op_id.split(":")[-1],
        "locator": locator,
        "level": "CODE",
        "location": "IN_REPOSITORY",
        "depends_on": [],
        "description": op_id,
    }


def _changeset(*ops: dict) -> dict:
    return {"snapshot_id": "snap-1", "operations": list(ops), "skipped": [], "issues": []}


def _task(task_id: str, covers: list[str], status: TaskStatus = TaskStatus.COMPLETED) -> Task:
    return Task(id=task_id, title=task_id, status=status, covers=covers)


def _check_state(reconciliation: Reconciliation, op_id: str) -> OperationState:
    for check in reconciliation.checks:
        if check.operation_id == op_id:
            return check.state
    raise AssertionError(f"no check for {op_id}")


class ReconcileTest(unittest.TestCase):
    def test_d1_incomplete_or_uncovered_coverage_is_pending(self) -> None:
        changeset = _changeset(
            _op("create:a", "CREATE_NODE"),
            _op("create:b", "CREATE_NODE"),
            _op("create:c", "CREATE_NODE"),
            _op("create:d", "CREATE_NODE"),
        )
        tasks = [
            _task("T-1", ["create:a"], status=TaskStatus.PENDING),
            _task("T-2", ["create:b"], status=TaskStatus.FAILED),
            _task("T-3", ["create:c"], status=TaskStatus.BLOCKED),
        ]
        result = reconcile(changeset, tasks, observed_ids=set(), observed_revision=1)
        for op_id in ("create:a", "create:b", "create:c", "create:d"):
            self.assertIs(_check_state(result, op_id), OperationState.PENDING)
        details = {check.operation_id: check.detail for check in result.checks}
        self.assertIn("T-2", details["create:b"])
        self.assertIn("uncovered", details["create:d"])

    def test_d2_create_states(self) -> None:
        changeset = _changeset(
            _op("create:seen", "CREATE_NODE", locator="tools/mod.py"),
            _op("create:missing", "CREATE_NODE", locator="tools/ghost.py"),
            _op("create:blind", "CREATE_NODE"),
        )
        tasks = [_task("T-1", ["create:seen", "create:missing", "create:blind"])]
        result = reconcile(changeset, tasks, observed_ids={"tools/mod.py"}, observed_revision=2)
        self.assertIs(_check_state(result, "create:seen"), OperationState.MATERIALIZED)
        self.assertIs(_check_state(result, "create:missing"), OperationState.DIVERGENT)
        self.assertIs(_check_state(result, "create:blind"), OperationState.UNVERIFIABLE)

    def test_d3_modify_and_remove_are_symmetric(self) -> None:
        changeset = _changeset(
            _op("change:alive", "MODIFY_NODE", locator="pkg/a.py"),
            _op("change:gone", "MODIFY_NODE", locator="pkg/b.py"),
            _op("remove:gone", "REMOVE_NODE", locator="pkg/c.py"),
            _op("remove:alive", "REMOVE_NODE", locator="pkg/d.py"),
        )
        tasks = [_task("T-1", [op["id"] for op in changeset["operations"]])]
        result = reconcile(changeset, tasks, observed_ids={"pkg/a.py", "pkg/d.py"}, observed_revision=3)
        self.assertIs(_check_state(result, "change:alive"), OperationState.MATERIALIZED)
        self.assertIs(_check_state(result, "change:gone"), OperationState.DIVERGENT)
        self.assertIs(_check_state(result, "remove:gone"), OperationState.MATERIALIZED)
        self.assertIs(_check_state(result, "remove:alive"), OperationState.DIVERGENT)

    def test_d4_relations_are_unverifiable(self) -> None:
        changeset = _changeset(
            _op("connect:a->b:uses", "CONNECT"),
            _op("disconnect:a->c:uses", "DISCONNECT"),
        )
        tasks = [_task("T-1", ["connect:a->b:uses", "disconnect:a->c:uses"])]
        result = reconcile(changeset, tasks, observed_ids=set(), observed_revision=1)
        self.assertIs(_check_state(result, "connect:a->b:uses"), OperationState.UNVERIFIABLE)
        self.assertIs(_check_state(result, "disconnect:a->c:uses"), OperationState.UNVERIFIABLE)


class MergeGateTest(unittest.TestCase):
    def test_d5_gate_blocks_selectively(self) -> None:
        changeset = _changeset(
            _op("create:ok", "CREATE_NODE", locator="pkg/ok.py"),
            _op("create:bad", "CREATE_NODE", locator="pkg/bad.py"),
        )
        tasks = [
            _task("T-1", ["create:ok"]),
            _task("T-2", ["create:bad"], status=TaskStatus.FAILED),
        ]
        result = reconcile(changeset, tasks, observed_ids={"pkg/ok.py"}, observed_revision=1)
        reasons = merge_gate_reasons(result, tasks)
        self.assertTrue(any("T-2" in reason for reason in reasons))
        self.assertTrue(any("create:bad" in reason for reason in reasons))

    def test_d5_gate_allows_unverifiable(self) -> None:
        changeset = _changeset(
            _op("create:ok", "CREATE_NODE", locator="pkg/ok.py"),
            _op("connect:a->b:uses", "CONNECT"),
        )
        tasks = [_task("T-1", ["create:ok", "connect:a->b:uses"])]
        result = reconcile(changeset, tasks, observed_ids={"pkg/ok.py"}, observed_revision=1)
        self.assertEqual(merge_gate_reasons(result, tasks), [])

    def test_cde_required_unverifiable_operation_blocks(self) -> None:
        operation = _op("create:required", "CREATE_NODE")
        operation["verification_level"] = "hard"
        result = reconcile(
            _changeset(operation),
            [_task("T-1", ["create:required"])],
            observed_ids=set(),
            observed_revision=1,
        )
        reasons = merge_gate_reasons(result, [_task("T-1", ["create:required"])])
        self.assertTrue(any("unverifiable" in reason for reason in reasons))

    def test_d6_reconciliation_serializes(self) -> None:
        changeset = _changeset(_op("create:x", "CREATE_NODE"))
        tasks = [_task("T-1", ["create:x"])]
        result = reconcile(changeset, tasks, observed_ids=set(), observed_revision=7)
        data = json.loads(result.to_json())
        self.assertEqual(data["snapshot_id"], "snap-1")
        self.assertEqual(data["observed_revision"], 7)
        self.assertEqual(data["checks"][0]["operation_id"], "create:x")
        self.assertEqual(data["checks"][0]["state"], "unverifiable")
        self.assertTrue(data["checks"][0]["detail"])


class MergeGateMissionTest(unittest.TestCase):
    def _run_mission(self, tmp: Path, changeset: dict) -> tuple:
        agent = FakeAgent(FilesystemArtifactStore(tmp / "harness"))
        services, context, git = make_services(tmp, MissionMode.HOTFIX, agent=agent)
        agent.artifacts = services.artifacts
        services.tasks.save([Task("T-1", "one", covers=[op["id"] for op in changeset["operations"]])])
        services.artifacts.write_text("changeset.json", json.dumps(changeset))
        result = MissionOrchestrator(services, context).run()
        return result, services, git

    def test_d7_divergence_blocks_merge_and_writes_reconciliation(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            changeset = _changeset(_op("create:ghost", "CREATE_NODE", locator="tools/ghost.py"))
            result, services, git = self._run_mission(tmp, changeset)
            self.assertEqual(result.outcome, MissionOutcome.COMPLETE)
            self.assertFalse(git.merged)
            data = json.loads(services.artifacts.read_text("reconciliation.json"))
            self.assertEqual(data["checks"][0]["state"], "divergent")
            notifier = services.notifier
            self.assertTrue(any("Merge gate" in message for message in notifier.messages))

    def test_d7_verifiable_or_unverifiable_only_merges(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            changeset = _changeset(_op("create:blind", "CREATE_NODE"))
            result, services, git = self._run_mission(tmp, changeset)
            self.assertEqual(result.outcome, MissionOutcome.COMPLETE)
            self.assertTrue(git.merged)
            self.assertTrue(services.artifacts.exists("reconciliation.json"))


if __name__ == "__main__":
    unittest.main()
