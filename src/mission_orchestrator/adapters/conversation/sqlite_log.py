from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from mission_orchestrator.domain.conversation import ConversationMessage, ConversationRole


_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversation_messages(
  sequence INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id TEXT UNIQUE NOT NULL,
  role TEXT NOT NULL,
  phase TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at TEXT NOT NULL
)
"""


class SqliteConversationLog:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(_SCHEMA)

    def append(
        self,
        role: ConversationRole,
        content: str,
        *,
        phase: str,
    ) -> ConversationMessage:
        if not content.strip():
            raise ValueError("conversation message must not be empty")
        message_id = uuid.uuid4().hex
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO conversation_messages(message_id, role, phase, content, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (message_id, role.value, phase, content, created_at),
            )
            sequence = int(cursor.lastrowid)
        return ConversationMessage(sequence, message_id, role, phase, content, created_at)

    def messages(
        self,
        *,
        after_sequence: int = 0,
        limit: int = 500,
    ) -> list[ConversationMessage]:
        selected_limit = min(max(limit, 1), 1000)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT sequence, message_id, role, phase, content, created_at "
                "FROM conversation_messages WHERE sequence > ? ORDER BY sequence LIMIT ?",
                (max(after_sequence, 0), selected_limit),
            ).fetchall()
        return [
            ConversationMessage(
                sequence=int(row[0]),
                message_id=str(row[1]),
                role=ConversationRole(str(row[2])),
                phase=str(row[3]),
                content=str(row[4]),
                created_at=str(row[5]),
            )
            for row in rows
        ]

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=5.0)