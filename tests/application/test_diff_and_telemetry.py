"""Acceptance tests for K10 - textual map diff and minimal telemetry.

Spec: docs/hero-v2/specs/K10-diff-telemetry.md (D1-D6; D7 is the pre-existing
suite: missions without a map emit nothing new).
"""

from __future__ import annotations

import sys
import tempfile
import unittest
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from mission_orchestrator.adapters.command_bus import QueueCommandBus
from mission_orchestrator.adapters.design.store import DesignStore
from mission_orchestrator.application.approval import ApprovalCoordinator, ApprovalOutcome
from mission_orchestrator.application.review_coordinator import ReviewCoordinator
from mission_orchestrator.domain.command import Command, CommandKind
from mission_orchestrator.domain.design import DesignEdge, DesignNode
from mission_orchestrator.domain.map_diff import render_map_diff
from mission_orchestrator.domain.mission import MissionMode
from mission_orchestrator.domain.task import Task

from tests.application.test_approval import FakeNotifier, _seed
from tests.application.test_orchestrator import FakeAgent, make_services


def _node(node_id: str, intent: str, locator: str | None = None) -> DesignNode:
    return DesignNode(
        id=node_id,
        label=node_id,
        level="CODE",
        provenance="AGENT",
        location="IN_REPOSITORY",
        intent=intent,
        locator=locator,
        description=f"desc {node_id}",
    )


class RecordingLogger:
    def __init__(self) -> None:
        self.metrics: list[dict] = []

    def log(self, message: str) -> None:
        return None

    def tool_call(self, name: str, input: dict) -> None:
        return None

    def metric(self, record: dict) -> None:
        self.metrics.append(record)

    def events(self, name: str) -> list[dict]:
        return [record for record in self.metrics if record.get("event") == name]


class RenderMapDiffTest(unittest.TestCase):
    def test_d1_renders_grouped_changes(self) -> None:
        nodes = [
            _node("new_mod", "CREATE", locator=None),
            _node("old_mod", "CHANGE", locator="pkg/old.py"),
            _node("dead_mod", "REMOVE", locator="pkg/dead.py"),
            _node("keep_a", "KEEP"),
            _node("keep_b", "KEEP"),
        ]
        edges = [
            DesignEdge("new_mod", "old_mod", "uses", "AGENT", "CREATE"),
            DesignEdge("keep_a", "keep_b", "uses", "AGENT", "KEEP"),
        ]
        text = render_map_diff(nodes, edges)
        self.assertIn("+ CREATE new_mod", text)
        self.assertIn("~ CHANGE old_mod (pkg/old.py)", text)
        self.assertIn("- REMOVE dead_mod (pkg/dead.py)", text)
        self.assertIn("= KEEP: 2", text)
        self.assertIn("+ new_mod -uses-> old_mod", text)
        self.assertNotIn("keep_a -uses-> keep_b", text)
        self.assertEqual(text, render_map_diff(nodes, edges))

    def test_d2_keep_only_map_has_no_changes(self) -> None:
        text = render_map_diff([_node("a", "KEEP")], [])
        self.assertIn("no proposed changes", text)


class ApprovalDiffAndTelemetryTest(unittest.TestCase):
    def test_d3_diff_precedes_summary_and_approval_event_is_emitted(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "mission").mkdir()
            (root / "project").mkdir()
            store = DesignStore(root / "mission" / "design.db")
            _seed(store)
            commands = QueueCommandBus()
            commands.publish(Command(CommandKind.APPROVE))
            notifier = FakeNotifier()
            logger = RecordingLogger()
            outcome = ApprovalCoordinator(
                store=store,
                commands=commands,
                notifier=notifier,
                harness_dir=root / "mission",
                project_scope_dir=root / "project",
                observed_revision=7,
                logger=logger,
            ).wait_for_approval()
            self.assertEqual(outcome.kind, ApprovalOutcome.APPROVED)
            diff_index = next(i for i, m in enumerate(notifier.messages) if "+ CREATE Cache" in m)
            summary_index = next(i for i, m in enumerate(notifier.messages) if "awaits approval" in m)
            self.assertLess(diff_index, summary_index)
            events = logger.events("approval")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["snapshot_id"], outcome.snapshot_id)
            self.assertEqual(events[0]["design_revision"], 1)
            self.assertEqual(events[0]["observed_revision"], 7)


class FakePhaseExecutor:
    """Stubs phase runs for review flows; REVIEW rewrites the audit verdict."""

    def __init__(self, artifacts, next_review_verdict: str = "APPROVED") -> None:
        self.artifacts = artifacts
        self.next_review_verdict = next_review_verdict
        self.phases: list[str] = []

    def run(self, phase, variables=None, complexity=None, retry_count=0):
        del complexity, retry_count
        self.phases.append(phase.value if hasattr(phase, "value") else str(phase))
        if "review" in str(phase.value if hasattr(phase, "value") else phase).lower():
            self.artifacts.write_text(
                "audit.md",
                f"# Audit\n\n## Verdict\n{self.next_review_verdict}\n\n**STATUS: DONE**\n",
            )
            self.artifacts.write_text("review-evidence.json", _review_evidence(self.next_review_verdict))

        class _Result:
            block = None

        return _Result()


class _NoopCompactor:
    def compact(self, label: str) -> None:
        return None


def _review_setup(tmp: Path, verdict: str):
    agent = FakeAgent(None)
    services, context, _git = make_services(tmp, MissionMode.HOTFIX, agent=agent)
    agent.artifacts = services.artifacts
    logger = RecordingLogger()
    services.logger = logger
    services.tasks.save([Task("T-1", "one")])
    services.artifacts.write_text("status.md", "# Status\n\n## Files\n- ok.py\n\n**STATUS: DONE**\n")
    services.artifacts.write_text("audit.md", f"# Audit\n\n## Verdict\n{verdict}\n\n**STATUS: DONE**\n")
    services.artifacts.write_text("review-evidence.json", _review_evidence(verdict))
    executor = FakePhaseExecutor(services.artifacts)
    coordinator = ReviewCoordinator(services, context, executor, _NoopCompactor())
    return coordinator, logger, services


def _review_evidence(verdict: str) -> str:
    approved = verdict.upper() == "APPROVED"
    return json.dumps(
        {
            "schema_version": 1,
            "claims": [],
            "checks": [
                {"id": "hardcoding", "status": "pass", "evidence_refs": ["ok.py:1"]},
                {"id": "special_casing", "status": "pass", "evidence_refs": ["ok.py:1"]},
                {"id": "scope", "status": "pass", "evidence_refs": ["status.md"]},
            ],
            "failures": []
            if approved
            else [
                {
                    "id": "F1",
                    "failure_type": "technical_bug",
                    "recoverability_lost_at_stage": "implement",
                    "evidence_refs": ["ok.py:1"],
                }
            ],
        }
    )


class ReviewTelemetryTest(unittest.TestCase):
    def test_d4_initial_verdicts_are_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            coordinator, logger, services = _review_setup(Path(raw), "APPROVED")
            self.assertIsNone(coordinator.commit_or_request_human(0, Task("T-1", "one")))
            verdicts = logger.events("review_verdict")
            self.assertEqual(len(verdicts), 1)
            self.assertEqual(verdicts[0]["task_id"], "T-1")
            self.assertEqual(verdicts[0]["verdict"], "APPROVED")
            self.assertEqual(verdicts[0]["attempt"], 1)
            self.assertEqual(logger.events("rework"), [])
            receipt = json.loads(services.artifacts.read_text("review-receipt.json"))
            self.assertEqual(receipt["verdict"], "APPROVED")
            self.assertTrue(receipt["audit"]["exists"])
            self.assertEqual(receipt["review_evidence"]["checks"][0]["id"], "hardcoding")

    def test_d4_minor_changes_emits_rework(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            coordinator, logger, _ = _review_setup(Path(raw), "MINOR CHANGES")
            self.assertIsNone(coordinator.commit_or_request_human(0, Task("T-1", "one")))
            self.assertEqual(logger.events("review_verdict")[0]["verdict"], "MINOR_CHANGES")
            reworks = logger.events("rework")
            self.assertEqual(len(reworks), 1)
            self.assertEqual(reworks[0]["cause"], "minor_changes")

    def test_d5_human_retry_emits_rework(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            coordinator, logger, services = _review_setup(Path(raw), "REJECTED")
            services.commands.publish(Command(CommandKind.RETRY, feedback="fix it"))
            self.assertIsNone(coordinator.commit_or_request_human(0, Task("T-1", "one")))
            reworks = logger.events("rework")
            self.assertEqual(len(reworks), 1)
            self.assertEqual(reworks[0]["cause"], "human_retry")


class ReconciliationTelemetryTest(unittest.TestCase):
    def test_d6_gate_event_reports_counts_and_outcome(self) -> None:
        import json

        from mission_orchestrator.application.orchestrator import MissionOrchestrator
        from mission_orchestrator.domain.task import TaskStatus

        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            agent = FakeAgent(None)
            services, context, git = make_services(tmp, MissionMode.HOTFIX, agent=agent)
            agent.artifacts = services.artifacts
            logger = RecordingLogger()
            services.logger = logger
            services.tasks.save([Task("T-1", "one", covers=["create:ghost"])])
            services.artifacts.write_text(
                "changeset.json",
                json.dumps(
                    {
                        "snapshot_id": "snap-1",
                        "operations": [
                            {
                                "id": "create:ghost",
                                "kind": "CREATE_NODE",
                                "target_node": "ghost",
                                "locator": "tools/ghost.py",
                                "level": "CODE",
                                "location": "IN_REPOSITORY",
                                "depends_on": [],
                                "description": "ghost",
                            }
                        ],
                        "skipped": [],
                        "issues": [],
                    }
                ),
            )
            MissionOrchestrator(services, context).run()
            events = logger.events("reconciliation")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["snapshot_id"], "snap-1")
            self.assertEqual(events[0]["gate"], "blocked")
            self.assertEqual(events[0]["counts"]["divergent"], 1)
            self.assertFalse(git.merged)


if __name__ == "__main__":
    unittest.main()
