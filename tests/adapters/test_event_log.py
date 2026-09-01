from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from mission_orchestrator.adapters.events.decorators import PublishingLogger, PublishingNotifier
from mission_orchestrator.adapters.events.sqlite_log import SqliteEventLog
from mission_orchestrator.domain.block import BlockKind, BlockReason
from mission_orchestrator.domain.result import MissionOutcome, MissionResult


class RecordingInner:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def notify(self, message: str) -> None:
        self.calls.append(("notify", message))

    def notify_result(self, result: MissionResult) -> None:
        self.calls.append(("notify_result", result))

    def log(self, message: str) -> None:
        self.calls.append(("log", message))

    def tool_call(self, name: str, input: dict) -> None:
        self.calls.append(("tool_call", name))

    def metric(self, record: dict) -> None:
        self.calls.append(("metric", record))


class BrokenPublisher:
    def publish(self, kind: str, payload: dict) -> None:
        raise RuntimeError("event store down")

    def events_since(self, after_id: int, limit: int = 200) -> list:
        raise RuntimeError("event store down")


class SqliteEventLogTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.mission_dir = Path(self._tmp.name)
        self.log = SqliteEventLog(self.mission_dir, mission="PROJ:feature-x")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_e1_publish_persists_and_roundtrips(self) -> None:
        self.log.publish("notification", {"message": "hola"})
        self.log.publish("approval", {"snapshot_id": "abc", "design_revision": 2})

        events = self.log.events_since(0)

        self.assertEqual([e.event_id for e in events], [1, 2])
        self.assertEqual(events[0].kind, "notification")
        self.assertEqual(events[0].mission, "PROJ:feature-x")
        self.assertEqual(events[0].payload, {"message": "hola"})
        self.assertEqual(events[1].payload, {"snapshot_id": "abc", "design_revision": 2})
        self.assertTrue(events[0].timestamp)

    def test_e2_correlation_extracted_from_payload(self) -> None:
        self.log.publish("review_verdict", {"task_id": "task-1", "verdict": "APPROVED"})
        self.log.publish("approval", {"snapshot_id": "snap-9"})
        self.log.publish("notification", {"message": "plain"})

        events = self.log.events_since(0)

        self.assertEqual(events[0].task_id, "task-1")
        self.assertIsNone(events[0].snapshot_id)
        self.assertEqual(events[1].snapshot_id, "snap-9")
        self.assertIsNone(events[1].task_id)
        self.assertIsNone(events[2].task_id)
        self.assertIsNone(events[2].snapshot_id)

    def test_e3_events_since_filters_orders_and_limits(self) -> None:
        for index in range(5):
            self.log.publish("notification", {"message": str(index)})

        tail = self.log.events_since(2)
        self.assertEqual([e.event_id for e in tail], [3, 4, 5])

        limited = self.log.events_since(0, limit=2)
        self.assertEqual([e.event_id for e in limited], [1, 2])

    def test_e4_events_survive_reopen(self) -> None:
        self.log.publish("notification", {"message": "before"})

        reopened = SqliteEventLog(self.mission_dir, mission="PROJ:feature-x")
        reopened.publish("notification", {"message": "after"})

        events = reopened.events_since(0)
        self.assertEqual([e.event_id for e in events], [1, 2])
        self.assertEqual(events[1].payload, {"message": "after"})

    def test_e7_publish_does_not_propagate_own_errors(self) -> None:
        self.log.publish("bad", {"payload": object()})  # not JSON-serializable


class PublishingDecoratorsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.events = SqliteEventLog(Path(self._tmp.name), mission="PROJ:feature-x")
        self.inner = RecordingInner()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_e5_notifier_publishes_and_delegates(self) -> None:
        notifier = PublishingNotifier(self.inner, self.events)
        notifier.notify("map ready")
        notifier.notify_result(
            MissionResult(outcome=MissionOutcome.COMPLETE, summary="done", completed=1, failed=0)
        )

        events = self.events.events_since(0)
        self.assertEqual([e.kind for e in events], ["notification", "mission_result"])
        self.assertEqual(events[0].payload, {"message": "map ready"})
        self.assertEqual(
            events[1].payload,
            {"outcome": "complete", "summary": "done", "completed": 1, "failed": 0},
        )
        self.assertEqual([call[0] for call in self.inner.calls], ["notify", "notify_result"])

    def test_e6_logger_metric_publishes_with_derived_kind(self) -> None:
        logger = PublishingLogger(self.inner, self.events)
        logger.metric({"event": "review_verdict", "task_id": "task-1", "verdict": "APPROVED"})
        logger.metric({"phase": "implement", "turns": 3, "input_tokens": 10, "output_tokens": 5})
        logger.metric({"tokens": 42})
        logger.log("phase start: spec")
        logger.tool_call("Read", {"file_path": "x"})

        events = self.events.events_since(0)
        # tool_call publishes since A2; log remains delegation-only.
        self.assertEqual([e.kind for e in events], ["review_verdict", "phase", "metric", "tool_call"])
        self.assertEqual(events[0].task_id, "task-1")
        self.assertEqual(
            [call[0] for call in self.inner.calls],
            ["metric", "metric", "metric", "log", "tool_call"],
        )

    def test_e7_bridges_survive_broken_publisher(self) -> None:
        notifier = PublishingNotifier(self.inner, BrokenPublisher())
        logger = PublishingLogger(self.inner, BrokenPublisher())

        notifier.notify("still delivered")
        notifier.notify_result(
            MissionResult(
                outcome=MissionOutcome.BLOCKED,
                summary="s",
                block=BlockReason(BlockKind.TIMEOUT, "spec", "x"),
            )
        )
        logger.metric({"event": "rework", "task_id": "task-1"})

        self.assertEqual(
            [call[0] for call in self.inner.calls],
            ["notify", "notify_result", "metric"],
        )


if __name__ == "__main__":
    unittest.main()
