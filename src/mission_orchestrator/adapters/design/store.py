from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from mission_orchestrator.adapters.analysis.sqlite_graph import SQLiteCodeGraph
from mission_orchestrator.domain.design import (
    ApplyResult,
    ApplyStatus,
    DesignEdge,
    DesignKind,
    DesignLevel,
    DesignNode,
    Intent,
    Location,
    OperationRecord,
    Provenance,
    Resolution,
    SnapshotResult,
)

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS design_nodes(
  id TEXT PRIMARY KEY,
  label TEXT NOT NULL,
  level TEXT NOT NULL,
  provenance TEXT NOT NULL,
  location TEXT NOT NULL,
  intent TEXT NOT NULL,
  parent_id TEXT,
  locator TEXT,
  description TEXT NOT NULL DEFAULT '',
  kind TEXT NOT NULL DEFAULT 'unknown',
  target_path TEXT NOT NULL DEFAULT '',
  qualified_name TEXT NOT NULL DEFAULT '',
  signature TEXT NOT NULL DEFAULT '',
  docstring TEXT NOT NULL DEFAULT '',
  satisfies_json TEXT NOT NULL DEFAULT '[]',
  acceptance_json TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS design_edges(
  source TEXT NOT NULL,
  target TEXT NOT NULL,
  relation TEXT NOT NULL,
  provenance TEXT NOT NULL,
  intent TEXT NOT NULL,
  PRIMARY KEY(source, target, relation)
);
CREATE TABLE IF NOT EXISTS design_meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS approvals(
  snapshot_id TEXT PRIMARY KEY,
  design_revision INTEGER NOT NULL,
  observed_revision INTEGER NOT NULL,
  created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS operations(
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  operation_id TEXT UNIQUE NOT NULL,
  author TEXT NOT NULL,
  ts TEXT NOT NULL,
  base_revision INTEGER NOT NULL,
  ops_json TEXT NOT NULL,
  status TEXT NOT NULL,
  result_revision INTEGER NOT NULL,
  detail TEXT NOT NULL DEFAULT ''
);
"""

_IMMUTABLE_NODE_FIELDS = {"provenance"}
_UPDATABLE_NODE_FIELDS = {
    "label",
    "level",
    "location",
    "intent",
    "parent_id",
    "locator",
    "description",
    "kind",
    "target_path",
    "qualified_name",
    "signature",
    "docstring",
    "satisfies",
    "acceptance",
}


class DesignStoreVersionError(RuntimeError):
    pass


class _ValidationError(ValueError):
    pass


class DesignStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if version == 1:
            self._migrate_v1_to_v2(connection)
            version = SCHEMA_VERSION
        if version in (0, SCHEMA_VERSION):
            connection.executescript(SCHEMA)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            connection.commit()
        else:
            connection.close()
            raise DesignStoreVersionError(
                f"design.db schema version {version} is not supported (expected {SCHEMA_VERSION}); "
                "authorial data is never migrated destructively - migrate manually"
            )
        return connection

    @staticmethod
    def _migrate_v1_to_v2(connection: sqlite3.Connection) -> None:
        migrations = (
            "ALTER TABLE design_nodes ADD COLUMN kind TEXT NOT NULL DEFAULT 'unknown'",
            "ALTER TABLE design_nodes ADD COLUMN target_path TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE design_nodes ADD COLUMN qualified_name TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE design_nodes ADD COLUMN signature TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE design_nodes ADD COLUMN docstring TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE design_nodes ADD COLUMN satisfies_json TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE design_nodes ADD COLUMN acceptance_json TEXT NOT NULL DEFAULT '[]'",
        )
        try:
            connection.execute("BEGIN IMMEDIATE")
            for statement in migrations:
                connection.execute(statement)
            connection.execute(
                "UPDATE design_nodes SET kind = CASE "
                "WHEN level = 'SYSTEM' THEN 'system' "
                "ELSE 'unknown' END"
            )
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    @contextmanager
    def _session(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def current_revision(self) -> int:
        with self._session() as connection:
            return self._revision(connection)

    @staticmethod
    def _revision(connection: sqlite3.Connection) -> int:
        row = connection.execute("SELECT value FROM design_meta WHERE key = 'design_revision'").fetchone()
        return int(row[0]) if row else 0

    def apply(
        self,
        *,
        operation_id: str,
        author: str,
        base_revision: int,
        operations: list[dict],
    ) -> ApplyResult:
        with self._session() as connection:
            previous = connection.execute(
                "SELECT status, result_revision, detail FROM operations WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
            if previous:
                return ApplyResult(ApplyStatus.DUPLICATE, int(previous[1]), str(previous[2]))

            revision = self._revision(connection)
            if base_revision != revision:
                return self._record(
                    connection, operation_id, author, base_revision, operations,
                    ApplyStatus.CONFLICT, revision,
                    f"base_revision {base_revision} != current {revision}",
                )

            connection.execute("SAVEPOINT batch")
            try:
                for operation in operations:
                    self._apply_operation(connection, operation)
            except _ValidationError as exc:
                connection.execute("ROLLBACK TO batch")
                connection.execute("RELEASE batch")
                return self._record(
                    connection, operation_id, author, base_revision, operations,
                    ApplyStatus.REJECTED, revision, str(exc),
                )
            connection.execute("RELEASE batch")
            new_revision = revision + 1
            connection.execute(
                "INSERT INTO design_meta(key, value) VALUES('design_revision', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(new_revision),),
            )
            return self._record(
                connection, operation_id, author, base_revision, operations,
                ApplyStatus.APPLIED, new_revision, "",
            )

    @staticmethod
    def _record(
        connection: sqlite3.Connection,
        operation_id: str,
        author: str,
        base_revision: int,
        operations: list[dict],
        status: ApplyStatus,
        revision: int,
        detail: str,
    ) -> ApplyResult:
        connection.execute(
            "INSERT INTO operations(operation_id, author, ts, base_revision, ops_json, status, result_revision, detail) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                operation_id,
                author,
                datetime.now(timezone.utc).isoformat(),
                base_revision,
                json.dumps(operations, ensure_ascii=False),
                status.value,
                revision,
                detail,
            ),
        )
        return ApplyResult(status, revision, detail)

    def _apply_operation(self, connection: sqlite3.Connection, operation: dict) -> None:
        kind = operation.get("op", "")
        if kind == "add_node":
            self._add_node(connection, operation)
        elif kind == "update_node":
            self._update_node(connection, operation)
        elif kind == "remove_node":
            self._remove_node(connection, operation)
        elif kind == "add_edge":
            self._add_edge(connection, operation)
        elif kind == "remove_edge":
            self._remove_edge(connection, operation)
        else:
            raise _ValidationError(f"unknown operation type: {kind!r}")

    def _add_node(self, connection: sqlite3.Connection, operation: dict) -> None:
        node_id = self._required(operation, "id")
        if self._node_exists(connection, node_id):
            raise _ValidationError(f"node already exists: {node_id}")
        level = self._enum_value(DesignLevel, self._required(operation, "level"), "level")
        provenance = self._enum_value(Provenance, self._required(operation, "provenance"), "provenance")
        location = self._enum_value(Location, self._required(operation, "location"), "location")
        intent = self._enum_value(Intent, self._required(operation, "intent"), "intent")
        kind = self._enum_value(
            DesignKind,
            operation.get("kind", self._legacy_kind(level)),
            "kind",
        )
        if "kind" in operation and kind == DesignKind.UNKNOWN.value:
            raise _ValidationError("new nodes require an exact kind")
        parent_id = operation.get("parent_id")
        if parent_id is not None and not self._node_exists(connection, parent_id):
            raise _ValidationError(f"parent does not exist: {parent_id}")
        connection.execute(
            "INSERT INTO design_nodes("
            "id, label, level, provenance, location, intent, parent_id, locator, description, "
            "kind, target_path, qualified_name, signature, docstring, satisfies_json, acceptance_json"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                node_id,
                str(operation.get("label", node_id)),
                level,
                provenance,
                location,
                intent,
                parent_id,
                operation.get("locator"),
                str(operation.get("description", "")),
                kind,
                str(operation.get("target_path", "")),
                str(operation.get("qualified_name", "")),
                str(operation.get("signature", "")),
                str(operation.get("docstring", "")),
                json.dumps(self._text_list(operation, "satisfies", maximum=100), ensure_ascii=False),
                json.dumps(self._text_list(operation, "acceptance", maximum=1000), ensure_ascii=False),
            ),
        )

    def _update_node(self, connection: sqlite3.Connection, operation: dict) -> None:
        node_id = self._required(operation, "id")
        if not self._node_exists(connection, node_id):
            raise _ValidationError(f"node does not exist: {node_id}")
        fields = {key: value for key, value in operation.items() if key not in {"op", "id"}}
        immutable = set(fields) & _IMMUTABLE_NODE_FIELDS
        if immutable:
            raise _ValidationError(f"immutable fields cannot be updated: {sorted(immutable)}")
        unknown = set(fields) - _UPDATABLE_NODE_FIELDS
        if unknown:
            raise _ValidationError(f"unknown node fields: {sorted(unknown)}")
        if "level" in fields:
            fields["level"] = self._enum_value(DesignLevel, fields["level"], "level")
        if "location" in fields:
            fields["location"] = self._enum_value(Location, fields["location"], "location")
        if "intent" in fields:
            fields["intent"] = self._enum_value(Intent, fields["intent"], "intent")
        if "kind" in fields:
            fields["kind"] = self._enum_value(DesignKind, fields["kind"], "kind")
            if fields["kind"] == DesignKind.UNKNOWN.value:
                raise _ValidationError("updated nodes require an exact kind")
        if "satisfies" in fields:
            fields["satisfies_json"] = json.dumps(
                self._text_list(fields, "satisfies", maximum=100),
                ensure_ascii=False,
            )
            del fields["satisfies"]
        if "acceptance" in fields:
            fields["acceptance_json"] = json.dumps(
                self._text_list(fields, "acceptance", maximum=1000),
                ensure_ascii=False,
            )
            del fields["acceptance"]
        if "parent_id" in fields and fields["parent_id"] is not None:
            if not self._node_exists(connection, fields["parent_id"]):
                raise _ValidationError(f"parent does not exist: {fields['parent_id']}")
        assignments = ", ".join(f"{key} = ?" for key in fields)
        connection.execute(
            f"UPDATE design_nodes SET {assignments} WHERE id = ?",
            (*fields.values(), node_id),
        )

    def _remove_node(self, connection: sqlite3.Connection, operation: dict) -> None:
        node_id = self._required(operation, "id")
        if not self._node_exists(connection, node_id):
            raise _ValidationError(f"node does not exist: {node_id}")
        connection.execute("DELETE FROM design_edges WHERE source = ? OR target = ?", (node_id, node_id))
        connection.execute("UPDATE design_nodes SET parent_id = NULL WHERE parent_id = ?", (node_id,))
        connection.execute("DELETE FROM design_nodes WHERE id = ?", (node_id,))

    def _add_edge(self, connection: sqlite3.Connection, operation: dict) -> None:
        source = self._required(operation, "source")
        target = self._required(operation, "target")
        relation = self._required(operation, "relation")
        for endpoint in (source, target):
            if not self._node_exists(connection, endpoint):
                raise _ValidationError(f"edge endpoint does not exist: {endpoint}")
        provenance = self._enum_value(Provenance, self._required(operation, "provenance"), "provenance")
        intent = self._enum_value(Intent, self._required(operation, "intent"), "intent")
        existing = connection.execute(
            "SELECT 1 FROM design_edges WHERE source = ? AND target = ? AND relation = ?",
            (source, target, relation),
        ).fetchone()
        if existing:
            raise _ValidationError(f"edge already exists: {source} -{relation}-> {target}")
        connection.execute(
            "INSERT INTO design_edges(source, target, relation, provenance, intent) VALUES (?, ?, ?, ?, ?)",
            (source, target, relation, provenance, intent),
        )

    def _remove_edge(self, connection: sqlite3.Connection, operation: dict) -> None:
        source = self._required(operation, "source")
        target = self._required(operation, "target")
        relation = self._required(operation, "relation")
        cursor = connection.execute(
            "DELETE FROM design_edges WHERE source = ? AND target = ? AND relation = ?",
            (source, target, relation),
        )
        if cursor.rowcount == 0:
            raise _ValidationError(f"edge does not exist: {source} -{relation}-> {target}")

    @staticmethod
    def _node_exists(connection: sqlite3.Connection, node_id: str) -> bool:
        return connection.execute("SELECT 1 FROM design_nodes WHERE id = ?", (node_id,)).fetchone() is not None

    @staticmethod
    def _required(operation: dict, key: str) -> str:
        value = operation.get(key)
        if not value:
            raise _ValidationError(f"missing required field: {key}")
        return str(value)

    @staticmethod
    def _enum_value(enum_cls, raw: object, field: str) -> str:
        try:
            return enum_cls(str(raw)).value
        except ValueError as exc:
            raise _ValidationError(f"invalid {field}: {raw!r}") from exc

    def nodes(
        self,
        *,
        level: str | None = None,
        parent_id: str | None = None,
        intent: str | None = None,
    ) -> list[DesignNode]:
        clauses: list[str] = []
        params: list[str] = []
        if level is not None:
            clauses.append("level = ?")
            params.append(level)
        if parent_id is not None:
            clauses.append("parent_id = ?")
            params.append(parent_id)
        if intent is not None:
            clauses.append("intent = ?")
            params.append(intent)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._session() as connection:
            rows = connection.execute(
                f"SELECT {self._node_columns()} "
                f"FROM design_nodes {where} ORDER BY id",
                params,
            ).fetchall()
        return [self._node_from_row(row) for row in rows]

    def edges(self) -> list[DesignEdge]:
        with self._session() as connection:
            rows = connection.execute(
                "SELECT source, target, relation, provenance, intent FROM design_edges ORDER BY source, target, relation"
            ).fetchall()
        return [DesignEdge(*row) for row in rows]

    def history(self) -> list[OperationRecord]:
        with self._session() as connection:
            rows = connection.execute(
                "SELECT seq, operation_id, author, base_revision, status, detail FROM operations ORDER BY seq"
            ).fetchall()
        return [
            OperationRecord(
                seq=row[0], operation_id=row[1], author=row[2],
                base_revision=row[3], status=ApplyStatus(row[4]), detail=row[5],
            )
            for row in rows
        ]

    def resolution_for(self, node: DesignNode, facts: SQLiteCodeGraph) -> Resolution:
        if node.location == Location.EXTERNAL.value:
            return Resolution.EXTERNAL
        if not node.locator:
            return Resolution.UNRESOLVED
        with facts.session() as connection:
            row = connection.execute("SELECT 1 FROM nodes WHERE id = ?", (node.locator,)).fetchone()
        return Resolution.RESOLVED if row else Resolution.UNRESOLVED

    def approve(
        self,
        *,
        base_revision: int,
        observed_revision: int,
        metadata: dict[str, object] | None = None,
    ) -> SnapshotResult:
        with self._session() as connection:
            revision = self._revision(connection)
            if base_revision != revision:
                return SnapshotResult(ApplyStatus.CONFLICT, None)
            payload = {
                **(metadata or {}),
                "design_revision": revision,
                "observed_revision": observed_revision,
                "nodes": [node.to_json() for node in self._nodes_in(connection)],
                "edges": [edge.__dict__ for edge in self._edges_in(connection)],
            }
            canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
            snapshot_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
            snapshot = {"snapshot_id": snapshot_id, **payload, "created": datetime.now(timezone.utc).isoformat()}
            connection.execute(
                "INSERT OR IGNORE INTO approvals(snapshot_id, design_revision, observed_revision, created) "
                "VALUES (?, ?, ?, ?)",
                (snapshot_id, revision, observed_revision, snapshot["created"]),
            )
            return SnapshotResult(ApplyStatus.APPLIED, snapshot)

    def _nodes_in(self, connection: sqlite3.Connection) -> list[DesignNode]:
        rows = connection.execute(
            f"SELECT {self._node_columns()} "
            "FROM design_nodes ORDER BY id"
        ).fetchall()
        return [self._node_from_row(row) for row in rows]

    @staticmethod
    def _legacy_kind(level: str) -> str:
        if level == DesignLevel.SYSTEM.value:
            return DesignKind.SYSTEM.value
        return DesignKind.UNKNOWN.value

    @staticmethod
    def _text_list(source: dict, field: str, *, maximum: int) -> list[str]:
        raw = source.get(field, [])
        if not isinstance(raw, list):
            raise _ValidationError(f"{field} must be a list")
        if len(raw) > 100:
            raise _ValidationError(f"{field} has too many items")
        values: list[str] = []
        for item in raw:
            value = str(item).strip()
            if not value:
                raise _ValidationError(f"{field} contains an empty item")
            if len(value) > maximum:
                raise _ValidationError(f"{field} item is too long")
            values.append(value)
        return values

    @staticmethod
    def _node_columns() -> str:
        return (
            "id, label, level, provenance, location, intent, parent_id, locator, description, "
            "kind, target_path, qualified_name, signature, docstring, satisfies_json, acceptance_json"
        )

    @staticmethod
    def _node_from_row(row: tuple) -> DesignNode:
        return DesignNode(
            id=row[0],
            label=row[1],
            level=row[2],
            provenance=row[3],
            location=row[4],
            intent=row[5],
            parent_id=row[6],
            locator=row[7],
            description=row[8],
            kind=row[9],
            target_path=row[10],
            qualified_name=row[11],
            signature=row[12],
            docstring=row[13],
            satisfies=tuple(json.loads(row[14])),
            acceptance=tuple(json.loads(row[15])),
        )

    def _edges_in(self, connection: sqlite3.Connection) -> list[DesignEdge]:
        rows = connection.execute(
            "SELECT source, target, relation, provenance, intent FROM design_edges ORDER BY source, target, relation"
        ).fetchall()
        return [DesignEdge(*row) for row in rows]
