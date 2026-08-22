from __future__ import annotations

import json
from pathlib import Path

from mission_orchestrator.domain.reconciliation import Reconciliation, merge_gate_reasons, reconcile
from mission_orchestrator.domain.task import Task
from mission_orchestrator.ports.artifacts import ArtifactStore


class Reconciler:
    """Compares the approved changeset with the observed graph and gates the merge."""

    def __init__(self, harness_dir: Path, artifacts: ArtifactStore) -> None:
        self.harness_dir = harness_dir
        self.artifacts = artifacts

    def evaluate(self, tasks: list[Task]) -> tuple[Reconciliation | None, list[str]]:
        raw = self.artifacts.read_text("changeset.json", default="")
        if not raw:
            return None, []
        changeset = json.loads(raw)
        reconciliation = reconcile(
            changeset,
            tasks,
            self._observed_ids(),
            self._observed_revision(),
            self._verified_relationships(changeset),
        )
        self.artifacts.write_text("reconciliation.json", reconciliation.to_json() + "\n")
        return reconciliation, merge_gate_reasons(reconciliation, tasks)

    def _verified_relationships(self, changeset: dict) -> set[tuple[str, str, str]]:
        raw = self.artifacts.read_text("contract-verification.json", default="")
        if not raw:
            return set()
        try:
            verification = json.loads(raw)
        except json.JSONDecodeError:
            return set()
        if not isinstance(verification, dict) or not verification.get("passed"):
            return set()
        checks = verification.get("checks", [])
        if not isinstance(checks, list):
            return set()
        verified: set[tuple[str, str, str]] = set()
        for operation in changeset.get("operations", []):
            if not isinstance(operation, dict) or operation.get("kind") != "CONNECT":
                continue
            source = str(operation.get("source", ""))
            relation = str(operation.get("relation", ""))
            target = str(operation.get("target", ""))
            expected_detail = f"{source} {relation} {target}"
            if any(
                isinstance(check, dict)
                and check.get("state") == "passed"
                and check.get("node_id") == source
                and check.get("field") == f"relationship.{relation}"
                and check.get("detail") == expected_detail
                for check in checks
            ):
                verified.add((source, relation, target))
        return verified

    def _facts_graph(self):
        facts_path = self.harness_dir / "code_graph.db"
        if not facts_path.exists():
            return None
        from mission_orchestrator.adapters.analysis.sqlite_graph import SQLiteCodeGraph

        return SQLiteCodeGraph(facts_path)

    def _observed_ids(self) -> set[str]:
        graph = self._facts_graph()
        if graph is None:
            return set()
        with graph.session() as connection:
            return {row[0] for row in connection.execute("SELECT id FROM nodes")}

    def _observed_revision(self) -> int:
        graph = self._facts_graph()
        return graph.observed_revision() if graph is not None else 0
