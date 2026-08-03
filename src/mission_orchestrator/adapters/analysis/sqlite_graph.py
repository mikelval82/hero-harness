from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes(id TEXT PRIMARY KEY, type TEXT, file TEXT);
CREATE TABLE IF NOT EXISTS edges(
  source TEXT,
  target TEXT,
  relation TEXT,
  PRIMARY KEY(source, target, relation)
);
CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY, mtime_ns INTEGER);
CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(id, type, file, tokenize='trigram');
"""


class SQLiteCodeGraph:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.executescript(SCHEMA)
        return connection

    def rebuild_fts(self, connection: sqlite3.Connection) -> None:
        connection.execute("DELETE FROM nodes_fts")
        connection.execute("INSERT INTO nodes_fts(id, type, file) SELECT id, type, file FROM nodes")

    def dependencies(self, node: str) -> list[tuple[str, str]]:
        with self.connect() as connection:
            return list(
                connection.execute(
                    "SELECT target, relation FROM edges WHERE source = ? ORDER BY relation, target",
                    (node,),
                )
            )

    def dependents(self, node: str) -> list[tuple[str, str]]:
        with self.connect() as connection:
            return list(
                connection.execute(
                    "SELECT source, relation FROM edges WHERE target = ? ORDER BY relation, source",
                    (node,),
                )
            )

    def find_node(self, pattern: str) -> list[tuple[str, str, str]]:
        with self.connect() as connection:
            like = f"%{pattern}%"
            return list(
                connection.execute(
                    "SELECT id, type, file FROM nodes WHERE id LIKE ? ORDER BY id LIMIT 50",
                    (like,),
                )
            )

    def dead_code(self) -> list[str]:
        with self.connect() as connection:
            return [
                row[0]
                for row in connection.execute(
                    """
                    SELECT n.id FROM nodes n
                    LEFT JOIN edges e ON e.target = n.id
                    WHERE n.type IN ('function', 'method', 'class') AND e.source IS NULL
                    ORDER BY n.id
                    """
                )
            ]

