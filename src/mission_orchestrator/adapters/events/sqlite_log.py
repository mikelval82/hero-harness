from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from mission_orchestrator.domain.event import MissionEvent

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    mission TEXT NOT NULL,
    kind TEXT NOT NULL,
    task_id TEXT,
    snapshot_id TEXT,
    payload TEXT NOT NULL
)
"""


class SqliteEventLog:
    def __init__(self, mission_dir: Path, mission: str) -> None:
        self.db_path = mission_dir / "events.db"
        self.mission = mission
        with self._connect() as conn:
            conn.execute(_SCHEMA)

    def publish(self, kind: str, payload: dict) -> None:
        try:
            record = json.dumps(payload, ensure_ascii=False)
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO events (ts, mission, kind, task_id, snapshot_id, payload) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        datetime.now().isoformat(timespec="seconds"),
                        self.mission,
                        kind,
                        _text_or_none(payload.get("task_id")),
                        _text_or_none(payload.get("snapshot_id")),
                        record,
                    ),
                )
        except Exception:
            pass

    def events_since(self, after_id: int, limit: int = 200) -> list[MissionEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, ts, mission, kind, task_id, snapshot_id, payload FROM events WHERE id > ? ORDER BY id ASC LIMIT ?",
                (after_id, limit),
            ).fetchall()
        return [
            MissionEvent(
                event_id=row[0],
                timestamp=row[1],
                mission=row[2],
                kind=row[3],
                payload=json.loads(row[6]),
                task_id=row[4],
                snapshot_id=row[5],
            )
            for row in rows
        ]

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)


def _text_or_none(value: object) -> str | None:
    return str(value) if value is not None else None
