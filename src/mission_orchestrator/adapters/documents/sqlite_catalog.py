from __future__ import annotations

import hashlib
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from mission_orchestrator.domain.document import (
    DocumentSaveResult,
    DocumentSaveStatus,
    DocumentVersion,
)


SCHEMA_VERSION = 1
_LOGICAL_ID = re.compile(r"^[a-z0-9][a-z0-9/_-]{0,199}$")
_SCHEMA = """
CREATE TABLE IF NOT EXISTS document_versions(
  logical_id TEXT NOT NULL,
  revision INTEGER NOT NULL,
  content TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  author TEXT NOT NULL,
  phase TEXT NOT NULL,
  task_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY(logical_id, revision)
);
CREATE TABLE IF NOT EXISTS document_heads(
  logical_id TEXT PRIMARY KEY,
  revision INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS document_writes(
  command_id TEXT PRIMARY KEY,
  logical_id TEXT NOT NULL,
  base_revision INTEGER NOT NULL,
  result_revision INTEGER NOT NULL,
  status TEXT NOT NULL,
  detail TEXT NOT NULL
);
"""


class DocumentCatalogVersionError(RuntimeError):
    pass


class SqliteDocumentCatalog:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version not in (0, SCHEMA_VERSION):
                raise DocumentCatalogVersionError(
                    f"documents.db schema version {version} is not supported "
                    f"(expected {SCHEMA_VERSION})"
                )
            connection.executescript(_SCHEMA)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def save(
        self,
        *,
        logical_id: str,
        content: str,
        author: str,
        base_revision: int,
        command_id: str,
        phase: str = "",
        task_id: str = "",
    ) -> DocumentSaveResult:
        self._validate_logical_id(logical_id)
        if not command_id.strip():
            raise ValueError("command_id must not be empty")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute(
                "SELECT status, result_revision, detail FROM document_writes WHERE command_id = ?",
                (command_id,),
            ).fetchone()
            current = self._head_revision(connection, logical_id)
            if previous is not None:
                return DocumentSaveResult(
                    DocumentSaveStatus.DUPLICATE,
                    int(previous[1]),
                    current,
                    str(previous[2]),
                )
            if base_revision != current:
                detail = f"base_revision {base_revision} != current {current}"
                self._record_write(
                    connection,
                    command_id,
                    logical_id,
                    base_revision,
                    current,
                    DocumentSaveStatus.CONFLICT,
                    detail,
                )
                return DocumentSaveResult(
                    DocumentSaveStatus.CONFLICT,
                    current,
                    current,
                    detail,
                )
            revision = current + 1
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            created_at = datetime.now(timezone.utc).isoformat()
            connection.execute(
                "INSERT INTO document_versions "
                "(logical_id, revision, content, content_hash, author, phase, task_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    logical_id,
                    revision,
                    content,
                    content_hash,
                    author,
                    phase,
                    task_id,
                    created_at,
                ),
            )
            connection.execute(
                "INSERT INTO document_heads(logical_id, revision) VALUES (?, ?) "
                "ON CONFLICT(logical_id) DO UPDATE SET revision = excluded.revision",
                (logical_id, revision),
            )
            self._record_write(
                connection,
                command_id,
                logical_id,
                base_revision,
                revision,
                DocumentSaveStatus.APPLIED,
                "",
            )
            return DocumentSaveResult(
                DocumentSaveStatus.APPLIED,
                revision,
                revision,
            )

    def get(self, logical_id: str, revision: int | None = None) -> DocumentVersion | None:
        self._validate_logical_id(logical_id)
        with self._connect() as connection:
            selected_revision = revision
            if selected_revision is None:
                selected_revision = self._head_revision(connection, logical_id)
            if selected_revision <= 0:
                return None
            row = connection.execute(
                "SELECT logical_id, revision, content, content_hash, author, phase, task_id, created_at "
                "FROM document_versions WHERE logical_id = ? AND revision = ?",
                (logical_id, selected_revision),
            ).fetchone()
        return self._version(row) if row is not None else None

    def list_latest(self) -> list[DocumentVersion]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT v.logical_id, v.revision, v.content, v.content_hash, v.author, "
                "v.phase, v.task_id, v.created_at "
                "FROM document_versions v "
                "JOIN document_heads h ON h.logical_id = v.logical_id AND h.revision = v.revision "
                "ORDER BY v.logical_id"
            ).fetchall()
        return [self._version(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=5.0)

    @staticmethod
    def _head_revision(connection: sqlite3.Connection, logical_id: str) -> int:
        row = connection.execute(
            "SELECT revision FROM document_heads WHERE logical_id = ?",
            (logical_id,),
        ).fetchone()
        return int(row[0]) if row is not None else 0

    @staticmethod
    def _record_write(
        connection: sqlite3.Connection,
        command_id: str,
        logical_id: str,
        base_revision: int,
        result_revision: int,
        status: DocumentSaveStatus,
        detail: str,
    ) -> None:
        connection.execute(
            "INSERT INTO document_writes "
            "(command_id, logical_id, base_revision, result_revision, status, detail) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                command_id,
                logical_id,
                base_revision,
                result_revision,
                status.value,
                detail,
            ),
        )

    @staticmethod
    def _validate_logical_id(logical_id: str) -> None:
        if not _LOGICAL_ID.fullmatch(logical_id) or "//" in logical_id:
            raise ValueError(f"invalid logical document id: {logical_id!r}")

    @staticmethod
    def _version(row: tuple) -> DocumentVersion:
        return DocumentVersion(
            logical_id=str(row[0]),
            revision=int(row[1]),
            content=str(row[2]),
            content_hash=str(row[3]),
            author=str(row[4]),
            phase=str(row[5]),
            task_id=str(row[6]),
            created_at=str(row[7]),
        )