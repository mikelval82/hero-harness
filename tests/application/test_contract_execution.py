from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from mission_orchestrator.adapters.filesystem.artifact_store import FilesystemArtifactStore
from mission_orchestrator.adapters.filesystem.session_store import FilesystemMissionSessionStore
from mission_orchestrator.application.contract_execution import (
    ContractExecutionService,
    ExecutionConflictError,
    ExecutionValidationError,
)
from mission_orchestrator.domain.mission import MissionMode
from mission_orchestrator.domain.session import MissionSession, MissionStage
from mission_orchestrator.domain.task import Task, TaskStatus

from tests.application.test_orchestrator import FakeAgent, make_services


class ContractExecutionServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        agent = FakeAgent(FilesystemArtifactStore(root / "initial"))
        self.services, self.context, _ = make_services(root, MissionMode.HOTFIX, agent=agent)
        agent.artifacts = self.services.artifacts
        self.sessions = FilesystemMissionSessionStore(self.services.artifacts)
        session = MissionSession(
            self.context.mission_tag,
            stage=MissionStage.READY,
            revision=5,
            approved_snapshot_id="snap-1",
        )
        self.services.artifacts.write_text("_session.json", json.dumps(session.to_json()))
        self.services.tasks.save(
            [
                Task(
                    "T-1",
                    "Implement notifier",
                    covers=["create:notifier"],
                    target_nodes=["notifier"],
                )
            ]
        )
        contract = {
            "schema_version": 1,
            "snapshot_id": "snap-1",
            "design_revision": 2,
            "brief": {"logical_id": "mission/brief", "revision": 3},
            "project": {
                "name": self.context.project_name,
                "path": str(self.context.project_dir),
            },
            "base_commit": "test-head",
            "task": {
                "id": "T-1",
                "title": "Implement notifier",
                "covers": ["create:notifier"],
                "dependencies": [],
                "target_nodes": ["notifier"],
            },
            "requirements": ["REQ-1"],
            "operations": [],
            "nodes": [
                {
                    "id": "notifier",
                    "kind": "class",
                    "target_path": "src/notifier.py",
                    "qualified_name": "Notifier",
                    "signature": "",
                    "docstring": "Send notifications.",
                    "location": "IN_REPOSITORY",
                }
            ],
            "relationships": [],
        }
        contract_path = "task-contracts/snap-1/T-1.json"
        self.services.artifacts.write_text(contract_path, json.dumps(contract, sort_keys=True))
        self.services.artifacts.write_text(
            "task-contracts/index.json",
            json.dumps(
                {
                    "schema_version": 1,
                    "snapshot_id": "snap-1",
                    "contracts": {"T-1": contract_path},
                }
            ),
        )
        self.service = ContractExecutionService(
            services=self.services,
            context=self.context,
            sessions=self.sessions,
        )

    def test_lists_and_reads_the_pinned_task_contract(self) -> None:
        listed = self.service.list_tasks()
        selected = self.service.get_task("T-1")

        self.assertEqual(listed["snapshot_id"], "snap-1")
        self.assertEqual(listed["tasks"][0]["id"], "T-1")
        self.assertEqual(selected["contract"]["brief"]["revision"], 3)
        self.assertIsNone(selected["execution"])

    def test_cde_a10_second_executor_is_rejected_without_replacing_lease(self) -> None:
        first = self.service.begin(task_id="T-1", actor="mcp")

        with self.assertRaisesRegex(ExecutionConflictError, first["execution_id"]):
            self.service.begin(task_id="T-1", actor="chat")

        self.assertEqual(self.service.current_execution()["execution_id"], first["execution_id"])
        self.assertEqual(self.service.current_execution()["actor"], "mcp")

    def test_validate_and_complete_records_evidence_and_completes_task(self) -> None:
        target = self.context.project_dir / "src" / "notifier.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('class Notifier:\n    """Send notifications."""\n', encoding="utf-8")
        execution = self.service.begin(task_id="T-1", actor="mcp")

        verification = self.service.validate(execution["execution_id"])
        completed = self.service.complete(execution["execution_id"])

        self.assertTrue(verification["passed"])
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["final_commit"], "test-head-1")
        self.assertEqual(completed["realization"]["status"], "accepted")
        self.assertEqual(completed["realization"]["nodes"], ["notifier"])
        self.assertEqual(
            json.loads(self.services.artifacts.read_text("design-realization.json"))["tasks"]["T-1"]["commit"],
            "test-head-1",
        )
        self.assertIs(self.services.tasks.load()[0].status, TaskStatus.COMPLETED)
        self.assertIs(self.sessions.load(self.context.mission_tag).stage, MissionStage.COMPLETED)

    def test_completion_receipt_combines_commits_and_new_workspace_changes(self) -> None:
        target = self.context.project_dir / "src" / "notifier.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('class Notifier:\n    """Send notifications."""\n', encoding="utf-8")
        self.services.git.workspace_changes = ["preexisting-helper.py"]
        execution = self.service.begin(task_id="T-1", actor="mcp")
        self.services.git.committed_changes = ["src/notifier.py"]
        self.services.git.workspace_changes = ["preexisting-helper.py", "new-note.txt"]

        completed = self.service.complete(execution["execution_id"])

        self.assertEqual(completed["baseline_changed_files"], ["preexisting-helper.py"])
        self.assertEqual(completed["changed_files"], ["new-note.txt", "src/notifier.py"])

    def test_completion_is_refused_when_common_verifier_fails(self) -> None:
        execution = self.service.begin(task_id="T-1", actor="mcp")

        with self.assertRaisesRegex(ExecutionValidationError, "target_path"):
            self.service.complete(execution["execution_id"])

        self.assertIs(self.services.tasks.load()[0].status, TaskStatus.PENDING)
        self.assertEqual(self.service.current_execution()["status"], "active")

    def test_report_blocker_releases_the_active_lease_with_history(self) -> None:
        execution = self.service.begin(task_id="T-1", actor="mcp")

        blocked = self.service.report_blocker(
            execution["execution_id"],
            "Contract omits retry behavior",
        )

        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["blocker"], "Contract omits retry behavior")
        replacement = self.service.begin(task_id="T-1", actor="chat")
        self.assertNotEqual(replacement["execution_id"], execution["execution_id"])

    def test_chat_patch_is_contract_scoped_and_optimistic(self) -> None:
        target = self.context.project_dir / "src" / "notifier.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        original = 'class Notifier:\n    """Old docs."""\n'
        target.write_text(original, encoding="utf-8")
        execution = self.service.begin(task_id="T-1", actor="chat")
        selected = self.service.read_file(execution["execution_id"], "src/notifier.py")

        patched = self.service.apply_patch(
            execution["execution_id"],
            path="src/notifier.py",
            expected_sha256=selected["sha256"],
            old_text='    """Old docs."""',
            new_text='    """Send notifications."""',
        )

        self.assertEqual(
            target.read_text(encoding="utf-8"),
            'class Notifier:\n    """Send notifications."""\n',
        )
        self.assertEqual(patched["path"], "src/notifier.py")
        self.assertNotEqual(patched["sha256"], hashlib.sha256(original.encode()).hexdigest())
        with self.assertRaisesRegex(ExecutionConflictError, "hash"):
            self.service.apply_patch(
                execution["execution_id"],
                path="src/notifier.py",
                expected_sha256=selected["sha256"],
                old_text="class Notifier:",
                new_text="class Changed:",
            )
        with self.assertRaisesRegex(ValueError, "approved contract"):
            self.service.read_file(execution["execution_id"], "README.md")

    def test_only_chat_actor_can_patch_and_checks_are_bounded(self) -> None:
        execution = self.service.begin(task_id="T-1", actor="mcp")
        with self.assertRaisesRegex(ExecutionConflictError, "chat"):
            self.service.read_file(execution["execution_id"], "src/notifier.py")
        self.service.report_blocker(execution["execution_id"], "handoff")
        chat = self.service.begin(task_id="T-1", actor="chat")

        result = self.service.run_checks(chat["execution_id"])

        self.assertEqual(result, {"configured": True, "passed": True})
        self.assertEqual(self.service.current_execution()["checks"], result)

    def test_mission_actor_records_lifecycle_without_owning_workflow_transition(self) -> None:
        current = MissionSession(
            self.context.mission_tag,
            stage=MissionStage.TASK_REVIEW,
            revision=8,
            approved_snapshot_id="snap-1",
            active_task_id="T-1",
        )
        self.services.artifacts.write_text("_session.json", json.dumps(current.to_json()))
        target = self.context.project_dir / "src" / "notifier.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('class Notifier:\n    """Send notifications."""\n', encoding="utf-8")

        execution = self.service.begin(task_id="T-1", actor="mission")
        completed = self.service.complete(execution["execution_id"], manage_workflow=False)

        self.assertEqual(completed["actor"], "mission")
        self.assertEqual(completed["status"], "completed")
        self.assertIs(self.services.tasks.load()[0].status, TaskStatus.PENDING)
        self.assertIs(self.sessions.load(self.context.mission_tag).stage, MissionStage.TASK_REVIEW)


if __name__ == "__main__":
    unittest.main()
