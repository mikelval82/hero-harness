from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from mission_orchestrator.adapters.command_bus import QueueCommandBus
from mission_orchestrator.adapters.design.store import DesignStore
from mission_orchestrator.application.approval import ApprovalCoordinator, ApprovalOutcome
from mission_orchestrator.domain.command import Command, CommandKind


class FakeNotifier:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def notify(self, message: str) -> None:
        self.messages.append(message)

    def notify_result(self, result) -> None:  # pragma: no cover - unused
        self.messages.append(str(result))


def _seed(store: DesignStore) -> None:
    store.apply(
        operation_id="seed",
        author="AGENT",
        base_revision=0,
        operations=[
            {
                "op": "add_node",
                "id": "svc",
                "label": "Service",
                "level": "SYSTEM",
                "provenance": "HUMAN",
                "location": "EXTERNAL",
                "intent": "KEEP",
            },
            {
                "op": "add_node",
                "id": "cache",
                "label": "Cache",
                "level": "SYSTEM",
                "provenance": "AGENT",
                "location": "IN_REPOSITORY",
                "intent": "CREATE",
            },
            {
                "op": "add_edge",
                "source": "svc",
                "target": "cache",
                "relation": "uses",
                "provenance": "AGENT",
                "intent": "CREATE",
            },
        ],
    )


class ApprovalTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.harness = root / "mission"
        self.project_scope = root / "project"
        self.harness.mkdir()
        self.project_scope.mkdir()
        self.store = DesignStore(self.harness / "design.db")
        self.commands = QueueCommandBus()
        self.notifier = FakeNotifier()
        self.coordinator = ApprovalCoordinator(
            store=self.store,
            commands=self.commands,
            notifier=self.notifier,
            harness_dir=self.harness,
            project_scope_dir=self.project_scope,
            observed_revision=7,
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_approve_creates_content_addressed_snapshot(self) -> None:
        _seed(self.store)
        result = self.store.approve(base_revision=1, observed_revision=7)
        self.assertEqual(result.status.value, "APPLIED")
        snapshot = result.snapshot
        self.assertEqual(snapshot["design_revision"], 1)
        self.assertEqual(snapshot["observed_revision"], 7)
        self.assertEqual({n["id"] for n in snapshot["nodes"]}, {"svc", "cache"})
        self.assertEqual(len(snapshot["edges"]), 1)
        self.assertTrue(snapshot["snapshot_id"])
        again = self.store.approve(base_revision=1, observed_revision=7)
        self.assertEqual(again.snapshot["snapshot_id"], snapshot["snapshot_id"])

    def test_approve_with_stale_revision_is_conflict(self) -> None:
        _seed(self.store)
        result = self.store.approve(base_revision=0, observed_revision=7)
        self.assertEqual(result.status.value, "CONFLICT")
        self.assertIsNone(result.snapshot)

    def test_coordinator_approves_and_writes_both_scopes(self) -> None:
        _seed(self.store)
        self.commands.publish(Command(CommandKind.APPROVE))
        outcome = self.coordinator.wait_for_approval()
        self.assertEqual(outcome.kind, ApprovalOutcome.APPROVED)
        mission_copy = self.harness / "approved_snapshot.json"
        self.assertTrue(mission_copy.exists())
        data = json.loads(mission_copy.read_text(encoding="utf-8"))
        durable = self.project_scope / "snapshots" / f"{data['snapshot_id']}.json"
        self.assertTrue(durable.exists())
        self.assertEqual(
            json.loads(durable.read_text(encoding="utf-8"))["snapshot_id"], data["snapshot_id"]
        )

    def test_coordinator_reject_writes_nothing(self) -> None:
        _seed(self.store)
        self.commands.publish(Command(CommandKind.REJECT, reason="not yet"))
        outcome = self.coordinator.wait_for_approval()
        self.assertEqual(outcome.kind, ApprovalOutcome.REJECTED)
        self.assertFalse((self.harness / "approved_snapshot.json").exists())

    def test_coordinator_abort(self) -> None:
        _seed(self.store)
        self.commands.publish(Command(CommandKind.ABORT, reason="stop"))
        outcome = self.coordinator.wait_for_approval()
        self.assertEqual(outcome.kind, ApprovalOutcome.ABORTED)

    def test_coordinator_defers_unexpected_commands(self) -> None:
        _seed(self.store)
        self.commands.publish(Command(CommandKind.ANSWER, text="unrelated"))
        self.commands.publish(Command(CommandKind.APPROVE))
        outcome = self.coordinator.wait_for_approval()
        self.assertEqual(outcome.kind, ApprovalOutcome.APPROVED)
        deferred = self.commands.get_nowait()
        self.assertIsNotNone(deferred)
        self.assertEqual(deferred.kind, CommandKind.ANSWER)
        self.assertEqual(deferred.text, "unrelated")


if __name__ == "__main__":
    unittest.main()
