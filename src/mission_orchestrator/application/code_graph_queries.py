from __future__ import annotations

import sqlite3
from pathlib import Path


MAX_CODE_GRAPH_ROWS = 200
CODE_GRAPH_ACTIONS = frozenset(
    {"find_nodes", "dependencies", "dependents", "impact_analysis", "dead_code"}
)
_FIELDS_BY_ACTION = {
    "find_nodes": {"action", "pattern", "limit"},
    "dependencies": {"action", "node", "limit"},
    "dependents": {"action", "node", "limit"},
    "impact_analysis": {"action", "node", "limit"},
    "dead_code": {"action", "limit"},
}


def query_mission_code_graph(harness_dir: Path, request: dict) -> dict[str, object]:
    """Run one bounded, parameterized query against this mission's observed graph."""
    action = _validate_request(request)
    graph_path = harness_dir / "code_graph.db"
    if not graph_path.is_file():
        raise ValueError("observed code graph is not available")
    connection = _open_read_only(graph_path)
    try:
        revision = _observed_revision(connection)
        columns, rows = _query(connection, action, request)
    finally:
        connection.close()
    return {
        "action": action,
        "observed_revision": revision,
        "count": len(rows),
        "columns": columns,
        "rows": [list(row) for row in rows],
    }


def _open_read_only(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.execute("PRAGMA query_only = ON")
    return connection


def _validate_request(request: dict) -> str:
    if not isinstance(request, dict):
        raise ValueError("code graph request must be an object")
    action = request.get("action")
    if action not in CODE_GRAPH_ACTIONS:
        raise ValueError(f"unsupported code graph action: {action!r}")
    unexpected = sorted(set(request) - _FIELDS_BY_ACTION[action])
    if unexpected:
        raise ValueError(f"unexpected field(s) for {action}: {', '.join(unexpected)}")
    return action


def _limit(request: dict) -> int:
    value = request.get("limit", MAX_CODE_GRAPH_ROWS)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_CODE_GRAPH_ROWS:
        raise ValueError(f"limit must be an integer between 1 and {MAX_CODE_GRAPH_ROWS}")
    return value


def _required_text(request: dict, field: str) -> str:
    value = request.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required for {request.get('action')}")
    return value.strip()


def _observed_revision(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT value FROM meta WHERE key = 'observed_revision'").fetchone()
    return int(row[0]) if row else 0


def _node_exists(connection: sqlite3.Connection, node: str) -> bool:
    return connection.execute("SELECT 1 FROM nodes WHERE id = ? LIMIT 1", (node,)).fetchone() is not None


def _literal_like(value: str) -> str:
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _query(connection: sqlite3.Connection, action: str, request: dict) -> tuple[list[str], list[tuple]]:
    limit = _limit(request)
    if action == "find_nodes":
        pattern = _required_text(request, "pattern")
        rows = connection.execute(
            "SELECT type, id, file FROM nodes WHERE LOWER(id) LIKE LOWER(?) ESCAPE '\\' "
            "ORDER BY id LIMIT ?",
            (_literal_like(pattern), limit),
        ).fetchall()
        return ["type", "id", "file"], rows

    if action in {"dependencies", "dependents", "impact_analysis"}:
        node = _required_text(request, "node")
        if not _node_exists(connection, node):
            raise ValueError(f"node not found: {node}")
        if action == "dependencies":
            rows = connection.execute(
                "SELECT e.relation, n.type, e.target, n.file FROM edges e "
                "JOIN nodes n ON n.id = e.target WHERE e.source = ? "
                "ORDER BY e.relation, e.target LIMIT ?",
                (node, limit),
            ).fetchall()
            return ["relation", "type", "id", "file"], rows
        if action == "dependents":
            rows = connection.execute(
                "SELECT e.relation, n.type, e.source, n.file FROM edges e "
                "JOIN nodes n ON n.id = e.source WHERE e.target = ? "
                "ORDER BY e.relation, e.source LIMIT ?",
                (node, limit),
            ).fetchall()
            return ["relation", "type", "id", "file"], rows
        rows = connection.execute(
            "WITH RECURSIVE impacted(id) AS ("
            " SELECT source FROM edges WHERE target = ?"
            " UNION SELECT e.source FROM edges e JOIN impacted i ON e.target = i.id"
            ") SELECT n.type, i.id, n.file FROM impacted i JOIN nodes n ON n.id = i.id "
            "WHERE i.id != ? ORDER BY i.id LIMIT ?",
            (node, node, limit),
        ).fetchall()
        return ["type", "id", "file"], rows

    rows = connection.execute(
        "SELECT n.type, n.id, n.file FROM nodes n WHERE n.type != 'module' "
        "AND NOT EXISTS (SELECT 1 FROM lexical_refs r WHERE r.target = n.name "
        "OR r.target LIKE '%.' || n.name) "
        "AND NOT EXISTS (SELECT 1 FROM edges e WHERE e.relation = 'inherits' "
        "AND (e.target = n.name OR e.target LIKE '%.' || n.name)) "
        "ORDER BY n.file, n.id LIMIT ?",
        (limit,),
    ).fetchall()
    return ["type", "id", "file"], rows
