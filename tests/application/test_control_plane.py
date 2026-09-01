from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from mission_orchestrator.adapters.documents.sqlite_catalog import SqliteDocumentCatalog
from mission_orchestrator.adapters.filesystem.artifact_store import FilesystemArtifactStore
from mission_orchestrator.adapters.filesystem.session_store import FilesystemMissionSessionStore
from mission_orchestrator.application.control_plane import MissionControlPlane
from mission_orchestrator.application.document_service import MissionDocumentService
from mission_orchestrator.application.interactive_task_coordinator import InteractiveTaskCoordinator
from mission_orchestrator.application.preparation_coordinator import PreparationCoordinator
from mission_orchestrator.domain.mission import MissionMode
from mission_orchestrator.domain.session import MissionSession, MissionStage
from tests.application.test_orchestrator import FakeAgent, make_services


class MissionControlPlaneTest(unittest.TestCase):
    def test_snapshot_and_writes_use_logical_contracts(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as raw:
            root = Path(raw)
            agent = FakeAgent(FilesystemArtifactStore(root / "initial"))
            services, context, _ = make_services(root, MissionMode.FULL, agent=agent)
            agent.artifacts = services.artifacts
            sessions = FilesystemMissionSessionStore(services.artifacts)
            catalog = SqliteDocumentCatalog(context.harness_dir / "documents.db")
            documents = MissionDocumentService(services.artifacts, catalog, services.events)
            control = MissionControlPlane(
                services=services,
                context=context,
                sessions=sessions,
                catalog=catalog,
                documents=documents,
                preparation=PreparationCoordinator(
                    services=services,
                    context=context,
                    sessions=sessions,
                    documents=documents,
                    catalog=catalog,
                ),
                tasks=InteractiveTaskCoordinator(
                    services=services,
                    context=context,
                    sessions=sessions,
                    documents=documents,
                ),
            )

            saved = control.save_document(
                logical_id="mission/idea",
                content="# Idea\n",
                base_revision=0,
                command_id="idea-1",
            )
            changed = control.apply_design(
                base_revision=0,
                operation_id="node-1",
                operations=[
                    {
                        "op": "add_node",
                        "id": "proposal:api",
                        "label": "API",
                        "level": "SYSTEM",
                        "provenance": "HUMAN",
                        "location": "IN_REPOSITORY",
                        "intent": "CREATE",
                    }
                ],
            )
            snapshot = control.snapshot()

            self.assertEqual(saved.revision, 1)
            self.assertEqual(control.document("mission/idea")["content"], "# Idea\n")
            self.assertEqual(changed["status"], "APPLIED")
            self.assertEqual(snapshot["mission"]["stage"], "draft")
            self.assertEqual(snapshot["documents"][0]["logical_id"], "mission/idea")
            self.assertEqual(control.design()["nodes"][0]["resolution"], "UNRESOLVED")

            ready = MissionSession(
                context.mission_tag,
                stage=MissionStage.READY,
                revision=4,
            )
            services.artifacts.write_text("_session.json", json.dumps(ready.to_json()))
            amended = control.apply_design(
                base_revision=changed["design_revision"],
                operation_id="node-2",
                operations=[
                    {
                        "op": "update_node",
                        "id": "proposal:api",
                        "description": "Changed while ready",
                    }
                ],
            )

            self.assertEqual(amended["amendment"], "required")
            self.assertEqual(control.snapshot()["mission"]["stage"], "amendment_review")


if __name__ == "__main__":
    unittest.main()