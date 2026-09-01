from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mission_orchestrator.adapters.documents.sqlite_catalog import SqliteDocumentCatalog
from mission_orchestrator.adapters.filesystem.artifact_store import FilesystemArtifactStore
from mission_orchestrator.application.document_service import MissionDocumentService
from mission_orchestrator.domain.document import DocumentSaveStatus


class RecordingEvents:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []

    def publish(self, kind: str, payload: dict) -> None:
        self.published.append((kind, payload))

    def events_since(self, after_id: int, limit: int = 200) -> list:
        return []


class MissionDocumentServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self.temporary.name)
        self.artifacts = FilesystemArtifactStore(root)
        self.catalog = SqliteDocumentCatalog(root / "documents.db")
        self.events = RecordingEvents()
        self.service = MissionDocumentService(self.artifacts, self.catalog, self.events)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_human_save_updates_alias_and_publishes_revision(self) -> None:
        result = self.service.save(
            logical_id="mission/idea",
            alias="idea.md",
            content="# Project idea\n",
            author="HUMAN",
            base_revision=0,
            command_id="idea-save-1",
        )

        self.assertEqual(result.status, DocumentSaveStatus.APPLIED)
        self.assertEqual(self.artifacts.read_text("idea.md"), "# Project idea\n")
        self.assertEqual(self.events.published[0][0], "document_version_created")

    def test_phase_alias_is_captured_once_per_content_hash(self) -> None:
        self.artifacts.write_text("brainstorm.md", "# Brainstorm\n")

        first = self.service.capture_mission_document(
            "mission/brainstorm",
            author="AGENT",
            phase="research",
        )
        duplicate = self.service.capture_mission_document(
            "mission/brainstorm",
            author="AGENT",
            phase="research",
        )

        self.assertEqual(first.status, DocumentSaveStatus.APPLIED)
        self.assertEqual(duplicate.status, DocumentSaveStatus.DUPLICATE)
        self.assertEqual(self.catalog.get("mission/brainstorm").revision, 1)

    def test_cde_brief_seed_has_a_distinct_logical_id_and_alias(self) -> None:
        alias, task_id = self.service.alias_for("mission/brief-seed")
        result = self.service.save(
            logical_id="mission/brief-seed",
            alias=alias,
            content="# Detailed input brief\n",
            author="HUMAN",
            base_revision=0,
            command_id="brief-seed-1",
        )

        self.assertEqual(task_id, "")
        self.assertEqual(alias, "brief-seed.md")
        self.assertEqual(result.status, DocumentSaveStatus.APPLIED)
        self.assertEqual(self.artifacts.read_text("brief-seed.md"), "# Detailed input brief\n")
        self.assertIsNone(self.catalog.get("mission/brief"))

    def test_contract_and_verification_are_versioned_task_documents(self) -> None:
        self.assertEqual(
            self.service.alias_for("task/t-1/contract"),
            ("task-contract.json", "t-1"),
        )
        self.assertEqual(
            self.service.alias_for("task/t-1/verification"),
            ("contract-verification.json", "t-1"),
        )


if __name__ == "__main__":
    unittest.main()
