from __future__ import annotations

import json
from datetime import datetime, timezone

from mission_orchestrator.ports.artifacts import ArtifactStore


REALIZATION_ARTIFACT = "design-realization.json"


class DesignRealizationStore:
    """Keeps execution evidence separate from immutable design intent."""

    def __init__(self, artifacts: ArtifactStore) -> None:
        self.artifacts = artifacts

    def view(self) -> dict[str, object]:
        payload = self._read()
        tasks = payload["tasks"]
        nodes: dict[str, dict[str, object]] = {}
        edges: dict[str, dict[str, object]] = {}
        for task_id, item in tasks.items():
            if not isinstance(item, dict):
                continue
            summary = {
                "task_id": task_id,
                "status": item.get("status", "verified"),
                "commit": item.get("commit", ""),
                "snapshot_id": item.get("snapshot_id", ""),
                "accepted_at": item.get("accepted_at", ""),
            }
            for node_id in item.get("nodes", []):
                if isinstance(node_id, str):
                    nodes[node_id] = summary
            for edge_key in item.get("edges", []):
                if isinstance(edge_key, str):
                    edges[edge_key] = summary
        return payload | {"nodes": nodes, "edges": edges}

    def record(
        self,
        *,
        task_id: str,
        contract: dict[str, object],
        commit: str,
        observed_revision: int,
        accepted: bool,
    ) -> dict[str, object]:
        payload = self._read()
        task = contract.get("task") if isinstance(contract.get("task"), dict) else {}
        nodes = sorted(
            {
                str(node["id"])
                for node in contract.get("nodes", [])
                if isinstance(node, dict) and node.get("id")
            }
        )
        edges = sorted(
            {
                self.edge_key(edge)
                for edge in contract.get("relationships", [])
                if isinstance(edge, dict) and self.edge_key(edge)
            }
        )
        entry = {
            "task_id": task_id,
            "task_title": str(task.get("title", "")),
            "snapshot_id": str(contract.get("snapshot_id", "")),
            "status": "accepted" if accepted else "verified",
            "commit": commit,
            "observed_revision": observed_revision,
            "accepted_at": datetime.now(timezone.utc).isoformat(),
            "nodes": nodes,
            "edges": edges,
            "operations": sorted(str(item) for item in task.get("covers", []) if item),
        }
        payload["tasks"][task_id] = entry
        self.artifacts.write_text(
            REALIZATION_ARTIFACT,
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        )
        return entry

    @staticmethod
    def edge_key(edge: dict[str, object]) -> str:
        source = str(edge.get("source", ""))
        target = str(edge.get("target", ""))
        relation = str(edge.get("relation", ""))
        return f"{source}|{target}|{relation}" if source and target and relation else ""

    def _read(self) -> dict[str, object]:
        raw = self.artifacts.read_text(REALIZATION_ARTIFACT, default="")
        if not raw:
            return {"schema_version": 1, "tasks": {}}
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {"schema_version": 1, "tasks": {}}
        if not isinstance(payload, dict) or not isinstance(payload.get("tasks"), dict):
            return {"schema_version": 1, "tasks": {}}
        return {"schema_version": 1, "tasks": dict(payload["tasks"])}
