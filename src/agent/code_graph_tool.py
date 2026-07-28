from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from src.analysis.code_graph_queries import (
    MAX_CODE_GRAPH_ROWS,
    open_graph_read_only,
    query_graph,
)

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


def _tool_code_graph(inp: dict, project_dir: Path, harness_dir: Path) -> str:
    del project_dir  # The database location is fixed by the active mission.
    try:
        with open_graph_read_only(Path(harness_dir) / "code_graph.db") as connection:
            columns, rows = query_graph(connection, inp)
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
