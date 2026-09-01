from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes(id TEXT PRIMARY KEY, type TEXT, file TEXT, name TEXT);
CREATE TABLE IF NOT EXISTS edges(
  source TEXT,
  target TEXT,
  relation TEXT,
  file TEXT,
  PRIMARY KEY(source, target, relation)
);
CREATE TABLE IF NOT EXISTS lexical_refs(
  source TEXT,
  target TEXT,
  relation TEXT,
  file TEXT,
  PRIMARY KEY(source, target, relation)
);
CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY, mtime_ns INTEGER);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(id, type, file, tokenize='trigram');
"""

_KNOWN_TABLES = ("nodes", "edges", "lexical_refs", "files", "meta", "nodes_fts")


class SQLiteCodeGraph:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if version != SCHEMA_VERSION:
            for table in _KNOWN_TABLES:
                connection.execute(f"DROP TABLE IF EXISTS {table}")
            connection.executescript(SCHEMA)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            connection.commit()
        return connection

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def rebuild_fts(self, connection: sqlite3.Connection) -> None:
        connection.execute("DELETE FROM nodes_fts")
        connection.execute("INSERT INTO nodes_fts(id, type, file) SELECT id, type, file FROM nodes")

    def bump_observed_revision(self, connection: sqlite3.Connection) -> int:
        connection.execute(
            "INSERT INTO meta(key, value) VALUES('observed_revision', '1') "
            "ON CONFLICT(key) DO UPDATE SET value = CAST(value AS INTEGER) + 1"
        )
        row = connection.execute("SELECT value FROM meta WHERE key = 'observed_revision'").fetchone()
        return int(row[0])

    def observed_revision(self) -> int:
        with self.session() as connection:
            row = connection.execute(
                "SELECT value FROM meta WHERE key = 'observed_revision'"
            ).fetchone()
            return int(row[0]) if row else 0

    def dependencies(self, node: str) -> list[tuple[str, str]]:
        with self.session() as connection:
            return list(
                connection.execute(
                    "SELECT target, relation FROM edges WHERE source = ? "
                    "UNION SELECT target, relation FROM lexical_refs WHERE source = ? "
                    "ORDER BY relation, target",
                    (node, node),
                )
            )

    def dependents(self, node: str) -> list[tuple[str, str]]:
        with self.session() as connection:
            return list(
                connection.execute(
                    "SELECT source, relation FROM edges WHERE target = ? "
                    "UNION SELECT source, relation FROM lexical_refs WHERE target = ? "
                    "ORDER BY relation, source",
                    (node, node),
                )
            )

    def find_node(self, pattern: str) -> list[tuple[str, str, str]]:
        with self.session() as connection:
            like = f"%{pattern}%"
            return list(
                connection.execute(
                    "SELECT id, type, file FROM nodes WHERE id LIKE ? ORDER BY id LIMIT 50",
                    (like,),
                )
            )

    def dead_code(self) -> list[str]:
        with self.session() as connection:
            return [
                row[0]
                for row in connection.execute(
                    """
                    SELECT n.id FROM nodes n
                    WHERE n.type IN ('function', 'method', 'class')
                    AND NOT EXISTS (
                        SELECT 1 FROM lexical_refs r
                        WHERE r.target = n.name OR r.target LIKE '%.' || n.name
                    )
                    AND NOT EXISTS (
                        SELECT 1 FROM edges e
                        WHERE e.relation = 'inherits'
                        AND (e.target = n.name OR e.target LIKE '%.' || n.name)
                    )
                    ORDER BY n.id
                    """
                )
            ]

