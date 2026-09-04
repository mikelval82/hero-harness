from __future__ import annotations

import json
from pathlib import Path

from mission_orchestrator.adapters.analysis.sqlite_graph import SQLiteCodeGraph
from mission_orchestrator.domain.changeset import ChangeSet, changeset_to_json, compile_changeset
from mission_orchestrator.ports.artifacts import ArtifactStore


class PlanCompiler:
    """Materializes changeset.json from the approved snapshot and observed facts."""

    def __init__(self, harness_dir: Path, artifacts: ArtifactStore) -> None:
        self.harness_dir = harness_dir
        self.artifacts = artifacts

    def compile(self) -> ChangeSet | None:
        raw = self.artifacts.read_text("approved_snapshot.json", default="")
        if not raw:
            return None
        snapshot = json.loads(raw)
        changeset = compile_changeset(snapshot, self._observed_ids())
        self.artifacts.write_text("changeset.json", changeset_to_json(changeset) + "\n")
        return changeset

    def _observed_ids(self) -> set[str]:
        facts_path = self.harness_dir / "code_graph.db"
        if not facts_path.exists():
            return set()
        graph = SQLiteCodeGraph(facts_path)
        with graph.session() as connection:
            # Design locators use repository-relative paths, while extracted
            # graph node ids are namespaced by the mission/project.  Accept
            # both representations when resolving CHANGE/REMOVE targets.
            observed: set[str] = set()
            for node_id, file_path in connection.execute("SELECT id, file FROM nodes"):
                observed.add(str(node_id))
                if file_path:
                    observed.add(str(file_path).replace("\\", "/"))
            return observed
