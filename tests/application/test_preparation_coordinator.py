from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
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
            context = replace(context, no_grill=False)
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

    def test_cde_brief_seed_can_start_research_and_approval_pins_brief(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as raw:
            root = Path(raw)
            agent = FakeAgent(FilesystemArtifactStore(root / "initial"))
            services, context, _ = make_services(root, MissionMode.FULL, agent=agent)
            context = replace(context, no_grill=False)
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

            seed = coordinator.save_brief_seed(
                content="# Detailed initial brief\n",
                expected_session_revision=0,
                base_document_revision=0,
                command_id="seed-1",
            )
            research = coordinator.run_research(expected_session_revision=seed.session.revision)
            grill = coordinator.run_grill(expected_session_revision=research.session.revision)
            stale = coordinator.approve_design_and_structure(
                expected_session_revision=grill.session.revision,
                base_design_revision=0,
                base_brief_revision=0,
            )
            self.assertFalse(stale.accepted)
            self.assertIn("brief revision conflict", stale.detail)

            structured = coordinator.approve_design_and_structure(
                expected_session_revision=grill.session.revision,
                base_design_revision=0,
                base_brief_revision=1,
            )
            snapshot = json.loads(services.artifacts.read_text("approved_snapshot.json"))

            self.assertTrue(structured.accepted)
            self.assertEqual(snapshot["brief"], {"logical_id": "mission/brief", "revision": 1})
            self.assertEqual(snapshot["project"]["name"], context.project_name)
            self.assertEqual(snapshot["project"]["path"], str(context.project_dir))
            self.assertEqual(snapshot["base_commit"], "test-head")
            self.assertEqual(catalog.get("mission/brief-seed").author, "HUMAN")
            self.assertEqual(catalog.get("mission/brief").author, "AGENT")

    def test_grill_can_be_skipped_and_research_becomes_working_brief(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as raw:
            root = Path(raw)
            agent = FakeAgent(FilesystemArtifactStore(root / "initial"))
            services, context, _ = make_services(root, MissionMode.FULL, agent=agent)
            context = replace(context, no_grill=False)
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
                command_id="idea-skip-grill",
            )
            research = coordinator.run_research(expected_session_revision=idea.session.revision)
            review = coordinator.skip_grill(expected_session_revision=research.session.revision)

            self.assertEqual(review.session.stage, MissionStage.DESIGN_REVIEW)
            self.assertEqual(agent.phases, ["research"])
            brief = catalog.get("mission/brief")
            self.assertIsNotNone(brief)
            self.assertEqual(brief.author, "SYSTEM")
            self.assertIn("Grill was skipped", brief.content)

    def test_no_grill_context_skips_gate_after_research(self) -> None:
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
                command_id="idea-auto-skip-grill",
            )
            review = coordinator.run_research(expected_session_revision=idea.session.revision)

            self.assertEqual(review.session.stage, MissionStage.DESIGN_REVIEW)
            self.assertEqual(agent.phases, ["research"])


if __name__ == "__main__":
    unittest.main()
