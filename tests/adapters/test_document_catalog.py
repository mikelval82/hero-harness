from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mission_orchestrator.adapters.documents.sqlite_catalog import SqliteDocumentCatalog
from mission_orchestrator.domain.document import DocumentSaveStatus


class DocumentCatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.catalog = SqliteDocumentCatalog(Path(self.temporary.name) / "documents.db")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_applies_versions_and_lists_latest_content(self) -> None:
        first = self.catalog.save(
            logical_id="mission/idea",
            content="# Idea\n",
            author="HUMAN",
            base_revision=0,
            command_id="save-1",
        )
        second = self.catalog.save(
            logical_id="mission/idea",
            content="# Better idea\n",
            author="HUMAN",
            base_revision=1,
            command_id="save-2",
        )

        self.assertEqual(first.status, DocumentSaveStatus.APPLIED)
        self.assertEqual(second.revision, 2)
        self.assertEqual(self.catalog.get("mission/idea").content, "# Better idea\n")
        self.assertEqual(self.catalog.get("mission/idea", 1).content, "# Idea\n")
        self.assertEqual([item.logical_id for item in self.catalog.list_latest()], ["mission/idea"])

    def test_stale_revision_conflicts_without_changing_content(self) -> None:
        self.catalog.save(
            logical_id="task/t-1/spec",
            content="v1",
            author="AGENT",
            base_revision=0,
            command_id="agent-1",
            phase="spec",
            task_id="T-1",
        )

        result = self.catalog.save(
            logical_id="task/t-1/spec",
            content="stale",
            author="HUMAN",
            base_revision=0,
            command_id="human-1",
        )

        self.assertEqual(result.status, DocumentSaveStatus.CONFLICT)
        self.assertEqual(result.current_revision, 1)
        self.assertEqual(self.catalog.get("task/t-1/spec").content, "v1")

    def test_duplicate_command_is_idempotent(self) -> None:
        body = {
            "logical_id": "mission/brief",
            "content": "brief",
            "author": "AGENT",
            "base_revision": 0,
            "command_id": "grill-1",
        }
        first = self.catalog.save(**body)
        duplicate = self.catalog.save(**body)

        self.assertEqual(first.status, DocumentSaveStatus.APPLIED)
        self.assertEqual(duplicate.status, DocumentSaveStatus.DUPLICATE)
        self.assertEqual(duplicate.revision, 1)
        self.assertEqual(len(self.catalog.list_latest()), 1)


if __name__ == "__main__":
    unittest.main()