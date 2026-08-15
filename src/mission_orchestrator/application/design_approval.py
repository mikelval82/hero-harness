from __future__ import annotations

import json
from dataclasses import dataclass

from mission_orchestrator.adapters.design.store import DesignStore
from mission_orchestrator.adapters.analysis.sqlite_graph import SQLiteCodeGraph
from mission_orchestrator.application.plan_compiler import PlanCompiler
from mission_orchestrator.domain.design import ApplyStatus
from mission_orchestrator.ports.artifacts import ArtifactStore
from mission_orchestrator.ports.events import EventPublisher


@dataclass(frozen=True)
class DesignApprovalResult:
    status: ApplyStatus
    design_revision: int
    observed_revision: int
    snapshot_id: str = ""


class DesignApprovalService:
    def __init__(
        self,
        *,
        harness_dir,
        project_scope_dir,
        artifacts: ArtifactStore,
        events: EventPublisher,
    ) -> None:
        self.harness_dir = harness_dir
        self.project_scope_dir = project_scope_dir
        self.artifacts = artifacts
        self.events = events

    def approve(self, *, base_revision: int) -> DesignApprovalResult:
        store = DesignStore(self.harness_dir / "design.db")
        observed_revision = self._observed_revision()
        result = store.approve(
            base_revision=base_revision,
            observed_revision=observed_revision,
        )
        if result.status is not ApplyStatus.APPLIED or result.snapshot is None:
            return DesignApprovalResult(
                result.status,
                store.current_revision(),
                observed_revision,
            )
        snapshot = result.snapshot
        payload = json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n"
        self.artifacts.write_text("approved_snapshot.json", payload)
        if self.project_scope_dir is not None:
            durable = self.project_scope_dir / "snapshots"
            durable.mkdir(parents=True, exist_ok=True)
            (durable / f"{snapshot['snapshot_id']}.json").write_text(payload, encoding="utf-8")
        PlanCompiler(self.harness_dir, self.artifacts).compile()
        self.events.publish(
            "design_approved",
            {
                "snapshot_id": snapshot["snapshot_id"],
                "design_revision": snapshot["design_revision"],
                "observed_revision": snapshot["observed_revision"],
            },
        )
        return DesignApprovalResult(
            ApplyStatus.APPLIED,
            int(snapshot["design_revision"]),
            int(snapshot["observed_revision"]),
            str(snapshot["snapshot_id"]),
        )

    def _observed_revision(self) -> int:
        facts_path = self.harness_dir / "code_graph.db"
        if not facts_path.exists():
            return 0
        return SQLiteCodeGraph(facts_path).observed_revision()