from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from mission_orchestrator.adapters.documents.sqlite_catalog import SqliteDocumentCatalog
from mission_orchestrator.adapters.filesystem.artifact_store import FilesystemArtifactStore
from mission_orchestrator.adapters.filesystem.session_store import FilesystemMissionSessionStore
from mission_orchestrator.application.document_service import MissionDocumentService
from mission_orchestrator.application.interactive_task_coordinator import InteractiveTaskCoordinator
from mission_orchestrator.application.preparation_coordinator import PreparationResult
from mission_orchestrator.domain.mission import MissionMode
from mission_orchestrator.domain.session import MissionSession, MissionStage
from mission_orchestrator.domain.task import Task, TaskStatus
from tests.application.test_orchestrator import FakeAgent, make_services


class InteractiveTaskCoordinatorTest(unittest.TestCase):
    def test_mission_blocker_preserves_common_verifier_evidence(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as raw:
            root = Path(raw)
            agent = FakeAgent(FilesystemArtifactStore(root / "initial"))
            services, context, _ = make_services(root, MissionMode.FOCUSED, agent=agent)
            agent.artifacts = services.artifacts
            services.tasks.save([Task("T-1", "Implement notifier")])
            contract_path = "task-contracts/snap-1/T-1.json"
            services.artifacts.write_text(
                contract_path,
                json.dumps(
                    {
                        "schema_version": 1,
                        "snapshot_id": "snap-1",
                        "task": {"id": "T-1"},
                        "nodes": [
                            {
                                "id": "notifier",
                                "kind": "class",
                                "target_path": "src/notifier.py",
                                "qualified_name": "Notifier",
                                "docstring": "Send notifications.",
                            }
                        ],
                        "relationships": [],
                    }
                ),
            )
            services.artifacts.write_text(
                "task-contracts/index.json",
                json.dumps(
                    {
                        "schema_version": 1,
                        "snapshot_id": "snap-1",
                        "contracts": {"T-1": contract_path},
                    }
                ),
            )
            review = MissionSession(
                context.mission_tag,
                stage=MissionStage.TASK_REVIEW,
                revision=8,
                active_task_id="T-1",
                approved_snapshot_id="snap-1",
            )
            services.artifacts.write_text("_session.json", json.dumps(review.to_json()))
            sessions = FilesystemMissionSessionStore(services.artifacts)
            coordinator = InteractiveTaskCoordinator(
                services=services,
                context=context,
                sessions=sessions,
                documents=MissionDocumentService(
                    services.artifacts,
                    SqliteDocumentCatalog(context.harness_dir / "documents.db"),
                    services.events,
                ),
            )
            lease = coordinator.executions.begin(task_id="T-1", actor="mission")
            blocked = review.move_to(MissionStage.EXECUTING).move_to(
                MissionStage.BLOCKED,
                blocked_reason="contract verification failed",
            )

            coordinator._close_mission_execution(
                str(lease["execution_id"]),
                PreparationResult(blocked, detail="contract verification failed"),
            )

            execution = coordinator.executions.current_execution()
            self.assertEqual(execution["status"], "blocked")
            self.assertEqual(execution["verifier"]["passed"], False)

    def test_retry_review_does_not_repeat_implementation(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as raw:
            root = Path(raw)
            agent = FakeAgent(FilesystemArtifactStore(root / "initial"))
            services, context, _ = make_services(root, MissionMode.FOCUSED, agent=agent)
            agent.artifacts = services.artifacts
            services.artifacts.write_text(
                "tasks.json",
                json.dumps(
                    [
                        {
                            "id": "T-1",
                            "title": "Implement one",
                            "complexity": "M",
                            "status": "failed",
                            "failure_reason": "max_turns | phase=review | maximum turns exceeded",
                        },
                        {
                            "id": "T-2",
                            "title": "Implement two",
                            "complexity": "S",
                            "status": "pending",
                        },
                    ]
                ),
            )
            blocked = MissionSession(
                context.mission_tag,
                stage=MissionStage.BLOCKED,
                revision=13,
                active_task_id="T-1",
                blocked_reason="max_turns | phase=review | maximum turns exceeded",
            )
            services.artifacts.write_text("_session.json", json.dumps(blocked.to_json()))
            services.artifacts.write_text("status.md", "# Status\n\n**STATUS: DONE**\n")
            sessions = FilesystemMissionSessionStore(services.artifacts)
            documents = MissionDocumentService(
                services.artifacts,
                SqliteDocumentCatalog(context.harness_dir / "documents.db"),
                services.events,
            )
            coordinator = InteractiveTaskCoordinator(
                services=services,
                context=context,
                sessions=sessions,
                documents=documents,
            )

            retried = coordinator.retry_review(expected_session_revision=13)

            self.assertEqual(agent.phases, ["review"])
            self.assertEqual(services.tasks.load()[0].status, TaskStatus.COMPLETED)
            self.assertEqual(retried.session.stage, MissionStage.READY)

    def test_task_documents_are_reviewed_before_code_execution(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as raw:
            root = Path(raw)
            agent = FakeAgent(FilesystemArtifactStore(root / "initial"))
            services, context, git = make_services(root, MissionMode.FULL, agent=agent)
            agent.artifacts = services.artifacts
            services.artifacts.write_text(
                "tasks.json",
                json.dumps(
                    [
                        {
                            "id": "T-1",
                            "title": "Implement one",
                            "complexity": "M",
                            "status": "pending",
                        }
                    ]
                ),
            )
            services.artifacts.write_text(
                "task-contracts/snapshot-1/T-1.json",
                json.dumps(
                    {
                        "schema_version": 1,
                        "snapshot_id": "snapshot-1",
                        "task": {"id": "T-1", "title": "Implement one"},
                        "nodes": [],
                        "relationships": [],
                    }
                ),
            )
            services.artifacts.write_text(
                "task-contracts/index.json",
                json.dumps(
                    {
                        "schema_version": 1,
                        "snapshot_id": "snapshot-1",
                        "contracts": {
                            "T-1": "task-contracts/snapshot-1/T-1.json",
                        },
                    }
                ),
            )
            ready = MissionSession(
                context.mission_tag,
                stage=MissionStage.READY,
                revision=4,
                approved_snapshot_id="snapshot-1",
            )
            services.artifacts.write_text("_session.json", json.dumps(ready.to_json()))
            sessions = FilesystemMissionSessionStore(services.artifacts)
            catalog = SqliteDocumentCatalog(context.harness_dir / "documents.db")
            documents = MissionDocumentService(services.artifacts, catalog, services.events)
            coordinator = InteractiveTaskCoordinator(
                services=services,
                context=context,
                sessions=sessions,
                documents=documents,
            )

            prepared = coordinator.prepare_next(expected_session_revision=4)

            self.assertEqual(prepared.session.stage, MissionStage.TASK_REVIEW)
            self.assertEqual(agent.phases, ["spec", "plan"])
            self.assertEqual(services.tasks.load()[0].status.value, "pending")

            executed = coordinator.execute_prepared(
                expected_session_revision=prepared.session.revision,
                task_id="T-1",
            )

            self.assertEqual(executed.session.stage, MissionStage.COMPLETED)
            self.assertEqual(agent.phases, ["spec", "plan", "implement", "review", "report"])
            self.assertEqual(services.tasks.load()[0].status.value, "completed")
            self.assertFalse(git.merged)
            execution = coordinator.executions.current_execution()
            self.assertEqual(execution["actor"], "mission")
            self.assertEqual(execution["status"], "completed")
            self.assertEqual(
                {item.logical_id for item in catalog.list_latest()},
                {
                    "mission/report",
                    "task/t-1/spec",
                    "task/t-1/plan",
                    "task/t-1/decisions",
                    "task/t-1/status",
                    "task/t-1/audit",
                    "task/t-1/contract",
                    "task/t-1/verification",
                },
            )

    def test_design_amendment_pauses_after_current_phase(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as raw:
            root = Path(raw)
            agent = FakeAgent(FilesystemArtifactStore(root / "initial"))
            services, context, _ = make_services(root, MissionMode.FULL, agent=agent)
            agent.artifacts = services.artifacts
            services.artifacts.write_text(
                "tasks.json",
                json.dumps(
                    [
                        {
                            "id": "T-1",
                            "title": "Implement one",
                            "complexity": "S",
                            "status": "pending",
                        }
                    ]
                ),
            )
            ready = MissionSession(context.mission_tag, stage=MissionStage.READY, revision=4)
            services.artifacts.write_text("_session.json", json.dumps(ready.to_json()))
            sessions = FilesystemMissionSessionStore(services.artifacts)
            catalog = SqliteDocumentCatalog(context.harness_dir / "documents.db")
            documents = MissionDocumentService(services.artifacts, catalog, services.events)
            coordinator = InteractiveTaskCoordinator(
                services=services,
                context=context,
                sessions=sessions,
                documents=documents,
            )
            prepared = coordinator.prepare_next(expected_session_revision=4)

            self.assertEqual(agent.phases, ["spec", "plan"])
            self.assertEqual(
                {item.logical_id for item in catalog.list_latest()},
                {"task/t-1/spec", "task/t-1/plan", "task/t-1/decisions"},
            )

            services.artifacts.write_text(
                "_amendment_pending.json",
                json.dumps({"design_revision": 2}),
            )

            paused = coordinator.execute_prepared(
                expected_session_revision=prepared.session.revision,
                task_id="T-1",
            )

            self.assertEqual(paused.session.stage, MissionStage.AMENDMENT_REVIEW)
            self.assertEqual(agent.phases, ["spec", "plan", "implement"])
            self.assertEqual(services.tasks.load()[0].status.value, "pending")
            self.assertFalse(services.artifacts.exists("_amendment_pending.json"))

    def test_reconciliation_blocks_the_task_before_it_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as raw:
            root = Path(raw)
            agent = FakeAgent(FilesystemArtifactStore(root / "initial"))
            services, context, git = make_services(root, MissionMode.FULL, agent=agent)
            agent.artifacts = services.artifacts
            services.artifacts.write_text(
                "tasks.json",
                json.dumps(
                    [
                        {
                            "id": "T-1",
                            "title": "Implement one",
                            "complexity": "S",
                            "status": "pending",
                            "covers": ["create:ghost"],
                        }
                    ]
                ),
            )
            services.artifacts.write_text(
                "changeset.json",
                json.dumps(
                    {
                        "snapshot_id": "snapshot-1",
                        "operations": [
                            {
                                "id": "create:ghost",
                                "kind": "CREATE_NODE",
                                "locator": "tools/ghost.py",
                            }
                        ],
                    }
                ),
            )
            ready = MissionSession(context.mission_tag, stage=MissionStage.READY, revision=4)
            services.artifacts.write_text("_session.json", json.dumps(ready.to_json()))
            sessions = FilesystemMissionSessionStore(services.artifacts)
            catalog = SqliteDocumentCatalog(context.harness_dir / "documents.db")
            documents = MissionDocumentService(services.artifacts, catalog, services.events)
            coordinator = InteractiveTaskCoordinator(
                services=services,
                context=context,
                sessions=sessions,
                documents=documents,
            )
            prepared = coordinator.prepare_next(expected_session_revision=4)

            blocked = coordinator.execute_prepared(
                expected_session_revision=prepared.session.revision,
                task_id="T-1",
            )

            self.assertEqual(blocked.session.stage, MissionStage.BLOCKED)
            self.assertIn("divergence: create:ghost", blocked.detail)
            self.assertIsNone(catalog.get("mission/report"))
            self.assertFalse(git.merged)


if __name__ == "__main__":
    unittest.main()
