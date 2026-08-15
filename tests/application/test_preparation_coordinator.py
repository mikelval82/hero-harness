from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mission_orchestrator.adapters.documents.sqlite_catalog import SqliteDocumentCatalog
from mission_orchestrator.adapters.filesystem.session_store import FilesystemMissionSessionStore
from mission_orchestrator.application.document_service import MissionDocumentService
from mission_orchestrator.application.preparation_coordinator import PreparationCoordinator
from mission_orchestrator.domain.session import MissionStage
from tests.application.test_orchestrator import FakeAgent, make_services
from mission_orchestrator.adapters.filesystem.artifact_store import FilesystemArtifactStore
from mission_orchestrator.domain.mission import MissionMode


class PreparationCoordinatorTest(unittest.TestCase):
    def test_preparation_is_incremental_and_versions_outputs(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as raw:
            root = Path(raw)
            agent = FakeAgent(FilesystemArtifactStore(root / "initial"))
            services, context, _ = make_services(root, MissionMode.FULL, agent=agent)
            agent.artifacts = services.artifacts
            catalog = SqliteDocumentCatalog(context.harness_dir / "documents.db")
            documents = MissionDocumentService(services.artifacts, catalog, services.events)
            coordinator = PreparationCoordinator(
                services=services,
                context=context,
                sessions=FilesystemMissionSessionStore(services.artifacts),
                documents=documents,
                catalog=catalog,
            )

            idea = coordinator.save_idea(
                content="# Build an order service\n",
                expected_session_revision=0,
                base_document_revision=0,
                command_id="idea-1",
            )
            research = coordinator.run_research(expected_session_revision=idea.session.revision)
            grill = coordinator.run_grill(expected_session_revision=research.session.revision)
            structured = coordinator.approve_design_and_structure(
                expected_session_revision=grill.session.revision,
                base_design_revision=0,
            )
            ready = coordinator.approve_execution(
                expected_session_revision=structured.session.revision,
            )

            self.assertEqual(ready.session.stage, MissionStage.READY)
            self.assertTrue(services.artifacts.exists("execution_approval.json"))
            self.assertEqual(
                {item.logical_id for item in catalog.list_latest()},
                {"mission/idea", "mission/brainstorm", "mission/brief", "mission/tasks"},
            )
            self.assertEqual(
                agent.phases,
                ["research", "grill", "structure"],
            )


if __name__ == "__main__":
    unittest.main()