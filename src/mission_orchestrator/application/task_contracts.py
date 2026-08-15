from __future__ import annotations

import json
import re

from mission_orchestrator.domain.task import Task
from mission_orchestrator.ports.artifacts import ArtifactStore


TASK_CONTRACT_INDEX = "task-contracts/index.json"
TASK_CONTRACT_ALIAS = "task-contract.json"
SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")


class TaskContractCompiler:
    """Compiles immutable, deterministic task views of an approved contract."""

    def __init__(self, artifacts: ArtifactStore) -> None:
        self.artifacts = artifacts

    def compile(self, tasks: list[Task]) -> dict[str, str]:
        snapshot = self._read_json("approved_snapshot.json")
        changeset = self._read_json("changeset.json")
        snapshot_id = str(snapshot.get("snapshot_id", ""))
        if not SAFE_SEGMENT.fullmatch(snapshot_id):
            raise ValueError(f"invalid snapshot id for task contracts: {snapshot_id!r}")
        if changeset.get("snapshot_id") != snapshot_id:
            raise ValueError("changeset snapshot does not match approved snapshot")
        issues = changeset.get("issues", [])
        if issues:
            raise ValueError("changeset has unresolved issues: " + "; ".join(self._issue(item) for item in issues))

        operations = {str(item["id"]): item for item in changeset.get("operations", [])}
        nodes = {str(item["id"]): item for item in snapshot.get("nodes", [])}
        paths: dict[str, str] = {}
        for task in sorted(tasks, key=lambda item: item.id):
            if not SAFE_SEGMENT.fullmatch(task.id):
                raise ValueError(f"invalid task id for contract artifact: {task.id!r}")
            covered = self._covered_operations(task, operations)
            target_ids = self._target_ids(task, covered, nodes)
            relationships = self._relationships(snapshot, target_ids)
            task_nodes = [nodes[node_id] for node_id in sorted(target_ids)]
            requirements = sorted(
                {
                    str(requirement)
                    for node in task_nodes
                    for requirement in node.get("satisfies", [])
                }
            )
            payload = {
                "schema_version": 1,
                "snapshot_id": snapshot_id,
                "design_revision": int(snapshot.get("design_revision", 0)),
                "brief": snapshot.get("brief", {}),
                "project": snapshot.get("project", {}),
                "base_commit": str(snapshot.get("base_commit", "")),
                "task": {
                    "id": task.id,
                    "title": task.title,
                    "covers": sorted(task.covers),
                    "dependencies": sorted(task.dependencies),
                    "target_nodes": sorted(target_ids),
                },
                "requirements": requirements,
                "operations": covered,
                "nodes": task_nodes,
                "relationships": relationships,
            }
            encoded = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
            path = f"task-contracts/{snapshot_id}/{task.id}.json"
            current = self.artifacts.read_text(path, default="")
            if current and current != encoded:
                raise ValueError(f"immutable task contract conflict: {task.id}")
            self.artifacts.write_text(path, encoded)
            paths[task.id] = path

        index = {
            "schema_version": 1,
            "snapshot_id": snapshot_id,
            "contracts": {task_id: paths[task_id] for task_id in sorted(paths)},
        }
        self.artifacts.write_text(
            TASK_CONTRACT_INDEX,
            json.dumps(index, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        )
        return paths

    def materialize(self, task_id: str) -> str:
        index = self._read_json(TASK_CONTRACT_INDEX)
        path = index.get("contracts", {}).get(task_id)
        if not path:
            raise ValueError(f"task contract not found: {task_id}")
        content = self.artifacts.read_text(str(path))
        self.artifacts.write_text(TASK_CONTRACT_ALIAS, content)
        return str(path)

    def _read_json(self, name: str) -> dict:
        raw = self.artifacts.read_text(name, default="")
        if not raw:
            raise ValueError(f"required contract artifact missing: {name}")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError(f"contract artifact must be an object: {name}")
        return value

    @staticmethod
    def _covered_operations(task: Task, operations: dict[str, dict]) -> list[dict]:
        unknown = sorted(set(task.covers) - operations.keys())
        if unknown:
            raise ValueError(f"task {task.id} covers unknown operation: {unknown[0]}")
        return [operations[operation_id] for operation_id in sorted(task.covers)]

    @staticmethod
    def _target_ids(task: Task, operations: list[dict], nodes: dict[str, dict]) -> set[str]:
        target_ids = set(task.target_nodes)
        for operation in operations:
            for key in ("target_node", "source", "target"):
                value = operation.get(key)
                if value:
                    target_ids.add(str(value))
        unknown = sorted(target_ids - nodes.keys())
        if unknown:
            raise ValueError(f"task {task.id} references unknown target node: {unknown[0]}")
        return target_ids

    @staticmethod
    def _relationships(snapshot: dict, target_ids: set[str]) -> list[dict]:
        relationships = []
        for edge in snapshot.get("edges", []):
            if edge.get("intent", "KEEP") == "REMOVE":
                continue
            if edge.get("source") not in target_ids and edge.get("target") not in target_ids:
                continue
            relation = str(edge.get("relation", "")).lower()
            if relation in {"contains", "inherits"}:
                verification = "hard"
            elif relation == "imports" and edge.get("provenance") == "ANALYZER":
                verification = "resolved"
            else:
                verification = "advisory"
            relationships.append(edge | {"verification_level": verification})
        return sorted(
            relationships,
            key=lambda edge: (
                str(edge.get("source", "")),
                str(edge.get("target", "")),
                str(edge.get("relation", "")),
            ),
        )

    @staticmethod
    def _issue(issue: object) -> str:
        if isinstance(issue, dict):
            return str(issue.get("detail", issue))
        return str(issue)
