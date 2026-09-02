from __future__ import annotations

import json
from dataclasses import dataclass

from mission_orchestrator.adapters.analysis.sqlite_graph import SQLiteCodeGraph
from mission_orchestrator.adapters.design.store import DesignStore
from mission_orchestrator.adapters.filesystem.artifact_store import FilesystemArtifactStore
from mission_orchestrator.application.code_graph_queries import (
    CODE_GRAPH_ACTIONS,
    MAX_CODE_GRAPH_ROWS,
    query_mission_code_graph,
)
from mission_orchestrator.adapters.tools.file_tools import _schema
from mission_orchestrator.ports.tool_registry import ToolAccess, ToolEnvironment

AGENT_AUTHOR = "AGENT"


@dataclass
class CodeGraphTool:
    """Read the fixed mission graph through the same contract as the worker API."""

    name: str = "CodeGraph"
    access: ToolAccess = ToolAccess.READ_ONLY

    def schema(self) -> dict:
        return _schema(
            self.name,
            "Read the observed code graph for this mission. The graph is pre-built, bounded, and "
            "read-only; source files remain authoritative.",
            {
                "action": {"type": "string", "enum": sorted(CODE_GRAPH_ACTIONS)},
                "pattern": {"type": "string"},
                "node": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": MAX_CODE_GRAPH_ROWS},
            },
            ["action"],
        )

    def execute(self, input: dict, env: ToolEnvironment) -> str:
        return json.dumps(query_mission_code_graph(env.harness_dir, input), ensure_ascii=False)


def _design_store(env: ToolEnvironment) -> DesignStore:
    return DesignStore(env.harness_dir / "design.db")


def _facts_graph(env: ToolEnvironment) -> SQLiteCodeGraph:
    return SQLiteCodeGraph(env.harness_dir / "code_graph.db")


@dataclass
class GraphQueryTool:
    name: str = "GraphQuery"
    access: ToolAccess = ToolAccess.READ_ONLY

    def schema(self) -> dict:
        return _schema(
            self.name,
            "Query the shared architecture map. scope='design' returns the editable design graph "
            "(nodes with computed resolution against observed code, edges, current design_revision). "
            "scope='facts' searches observed code declarations by pattern to anchor proposals.",
            {
                "scope": {"type": "string", "enum": ["design", "facts"]},
                "level": {"type": "string", "enum": ["SYSTEM", "PACKAGE", "CODE"]},
                "parent_id": {"type": "string"},
                "intent": {"type": "string", "enum": ["KEEP", "CREATE", "CHANGE", "REMOVE"]},
                "pattern": {"type": "string"},
            },
            ["scope"],
        )

    def execute(self, input: dict, env: ToolEnvironment) -> str:
        store = _design_store(env)
        revision = store.current_revision()
        scope = str(input.get("scope", "design"))
        if scope == "facts":
            pattern = str(input.get("pattern", ""))
            matches = _facts_graph(env).find_node(pattern) if pattern else []
            return json.dumps(
                {
                    "design_revision": revision,
                    "matches": [{"id": m[0], "type": m[1], "file": m[2]} for m in matches],
                },
                ensure_ascii=False,
            )
        facts = _facts_graph(env)
        nodes = store.nodes(
            level=input.get("level"),
            parent_id=input.get("parent_id"),
            intent=input.get("intent"),
        )
        return json.dumps(
            {
                "design_revision": revision,
                "nodes": [
                    {
                        "id": node.id,
                        "label": node.label,
                        "level": node.level,
                        "provenance": node.provenance,
                        "location": node.location,
                        "intent": node.intent,
                        "parent_id": node.parent_id,
                        "locator": node.locator,
                        "resolution": store.resolution_for(node, facts).value,
                    }
                    for node in nodes
                ],
                "edges": [
                    {
                        "source": edge.source,
                        "target": edge.target,
                        "relation": edge.relation,
                        "provenance": edge.provenance,
                        "intent": edge.intent,
                    }
                    for edge in store.edges()
                ],
            },
            ensure_ascii=False,
        )


@dataclass
class GraphProposeTool:
    name: str = "GraphPropose"
    access: ToolAccess = ToolAccess.HARNESS_MUTATION

    def schema(self) -> dict:
        return _schema(
            self.name,
            "Propose a validated, atomic batch of changes to the design map. "
            "base_revision must equal the current design_revision (from GraphQuery); on CONFLICT, "
            "re-query and rebuild the batch. operations support add_node, update_node, remove_node, "
            "add_edge, remove_edge. Nodes require id, label, level (SYSTEM|PACKAGE|CODE), provenance "
            "(HUMAN|AGENT|ANALYZER), location (IN_REPOSITORY|EXTERNAL), intent (KEEP|CREATE|CHANGE|REMOVE); "
            "optional parent_id, locator (observed node id like 'src/mod.py:Class'), description. "
            "For CREATE nodes, set locator to the expected observed id (e.g. the future file path) so "
            "the result can be verified after execution; without it the operation is unverifiable.",
            {
                "operation_id": {"type": "string"},
                "base_revision": {"type": "integer"},
                "operations": {"type": "array", "items": {"type": "object"}},
            },
            ["operation_id", "base_revision", "operations"],
        )

    def execute(self, input: dict, env: ToolEnvironment) -> str:
        store = _design_store(env)
        operations = input.get("operations") or []
        if not isinstance(operations, list):
            operations = []
        result = store.apply(
            operation_id=str(input["operation_id"]),
            author=AGENT_AUTHOR,
            base_revision=int(input.get("base_revision", -1)),
            operations=[op for op in operations if isinstance(op, dict)],
        )
        revision = result.revision if result.status.value != "CONFLICT" else store.current_revision()
        if result.status.value == "APPLIED":
            _request_execution_amendment(env, revision)
        return json.dumps(
            {"status": result.status.value, "design_revision": revision, "detail": result.detail},
            ensure_ascii=False,
        )


def _request_execution_amendment(env: ToolEnvironment, design_revision: int) -> None:
    """Turn an implementation-time graph change into a safe-boundary amendment."""
    session_path = env.harness_dir / "_session.json"
    try:
        session = json.loads(session_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if session.get("stage") not in {"executing", "reconciling"}:
        return
    FilesystemArtifactStore(env.harness_dir).write_text(
        "_amendment_pending.json",
        json.dumps(
            {
                "design_revision": design_revision,
                "requested_session_revision": session.get("revision", 0),
                "source": "mission_graph_proposal",
            },
            indent=2,
        )
        + "\n",
    )
