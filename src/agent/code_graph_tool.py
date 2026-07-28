from __future__ import annotations

import json
import sqlite3
from pathlib import Path


MAX_CODE_GRAPH_ROWS = 200

CODE_GRAPH_SCHEMA: dict = {
    "name": "CodeGraph",
    "description": (
        "Query the mission's pre-built code dependency graph. This tool is "
        "strictly read-only and never builds or modifies the graph."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "find_nodes",
                    "dependencies",
                    "dependents",
                    "impact_analysis",
                    "dead_code",
                ],
            },
            "pattern": {
                "type": "string",
                "description": "Literal substring used by find_nodes.",
            },
            "node": {
                "type": "string",
                "description": "Exact node id used by graph traversal actions.",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": MAX_CODE_GRAPH_ROWS,
                "description": "Maximum rows to return (default and hard maximum: 200).",
            },
        },
        "required": ["action"],
        "additionalProperties": False,
    },
}


def _open_read_only(db_path: Path) -> sqlite3.Connection:
    if not db_path.is_file():
        raise FileNotFoundError("code_graph.db is not available")
    connection = sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.execute("PRAGMA query_only = ON")
    return connection


def _limit(inp: dict) -> int:
    raw = inp.get("limit", MAX_CODE_GRAPH_ROWS)
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError("limit must be an integer between 1 and 200")
    if not 1 <= raw <= MAX_CODE_GRAPH_ROWS:
        raise ValueError("limit must be between 1 and 200")
    return raw


def _required_text(inp: dict, field: str) -> str:
    value = inp.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required for this action")
    return value.strip()


def _node_exists(connection: sqlite3.Connection, node: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM nodes WHERE id = ? LIMIT 1", (node,)
    ).fetchone() is not None


def _literal_like(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _query(connection: sqlite3.Connection, inp: dict) -> tuple[list[str], list[tuple]]:
    action = inp.get("action")
    limit = _limit(inp)

    if action == "find_nodes":
        pattern = _required_text(inp, "pattern")
        rows = connection.execute(
            "SELECT type, id, file FROM nodes "
            "WHERE LOWER(id) LIKE LOWER(?) ESCAPE '\\' "
            "ORDER BY id LIMIT ?",
            (_literal_like(pattern), limit),
        ).fetchall()
        return ["type", "id", "file"], rows

    if action in {"dependencies", "dependents", "impact_analysis"}:
        node = _required_text(inp, "node")
        if not _node_exists(connection, node):
            raise ValueError(f"node not found: {node}")

        if action == "dependencies":
            rows = connection.execute(
                "SELECT e.relation, n.type, e.target, n.file "
                "FROM edges e JOIN nodes n ON n.id = e.target "
                "WHERE e.source = ? ORDER BY e.target LIMIT ?",
                (node, limit),
            ).fetchall()
            return ["relation", "type", "id", "file"], rows

        if action == "dependents":
            rows = connection.execute(
                "SELECT e.relation, n.type, e.source, n.file "
                "FROM edges e JOIN nodes n ON n.id = e.source "
                "WHERE e.target = ? ORDER BY e.source LIMIT ?",
                (node, limit),
            ).fetchall()
            return ["relation", "type", "id", "file"], rows

        rows = connection.execute(
            "WITH RECURSIVE impacted(id) AS ("
            " SELECT source FROM edges WHERE target = ?"
            " UNION"
            " SELECT e.source FROM edges e JOIN impacted i ON e.target = i.id"
            ") "
            "SELECT n.type, i.id, n.file FROM impacted i "
            "JOIN nodes n ON n.id = i.id WHERE i.id != ? "
            "ORDER BY i.id LIMIT ?",
            (node, node, limit),
        ).fetchall()
        return ["type", "id", "file"], rows

    if action == "dead_code":
        rows = connection.execute(
            "SELECT n.type, n.id, n.file FROM nodes n "
            "WHERE n.type != 'module' AND NOT EXISTS ("
            " SELECT 1 FROM edges e"
            " WHERE e.target = n.id AND e.relation != 'defines'"
            ") ORDER BY n.file, n.id LIMIT ?",
            (limit,),
        ).fetchall()
        return ["type", "id", "file"], rows

    raise ValueError(f"unsupported action: {action!r}")


def _tool_code_graph(inp: dict, project_dir: Path, harness_dir: Path) -> str:
    del project_dir  # The database location is fixed by the active mission.
    try:
        with _open_read_only(Path(harness_dir) / "code_graph.db") as connection:
            columns, rows = _query(connection, inp)
        return json.dumps(
            {
                "action": inp.get("action"),
                "count": len(rows),
                "columns": columns,
                "rows": rows,
            },
            ensure_ascii=False,
        )
    except (FileNotFoundError, ValueError, sqlite3.Error, OSError) as exc:
        return f"Error: code graph unavailable: {exc}"
