from __future__ import annotations

import json
from dataclasses import dataclass

from mission_orchestrator.adapters.design.store import DesignStore
from mission_orchestrator.adapters.analysis.sqlite_graph import SQLiteCodeGraph
from mission_orchestrator.application.plan_compiler import PlanCompiler
from mission_orchestrator.domain.design import ApplyStatus
from mission_orchestrator.ports.artifacts import ArtifactStore
from mission_orchestrator.ports.documents import DocumentCatalog
from mission_orchestrator.ports.events import EventPublisher
from mission_orchestrator.ports.git_service import GitService


@dataclass(frozen=True)
class DesignApprovalResult:
    status: ApplyStatus
    design_revision: int
    observed_revision: int
    snapshot_id: str = ""
    brief_revision: int = 0
    base_commit: str = ""
    detail: str = ""


class DesignApprovalService:
    def __init__(
        self,
        *,
        harness_dir,
        project_scope_dir,
        artifacts: ArtifactStore,
        events: EventPublisher,
        catalog: DocumentCatalog,
        git: GitService,
        project_name: str,
        project_dir,
    ) -> None:
        self.harness_dir = harness_dir
        self.project_scope_dir = project_scope_dir
        self.artifacts = artifacts
        self.events = events
        self.catalog = catalog
        self.git = git
        self.project_name = project_name
        self.project_dir = project_dir

    def approve(
        self,
        *,
        base_revision: int,
        base_brief_revision: int | None = None,
    ) -> DesignApprovalResult:
        store = DesignStore(self.harness_dir / "design.db")
        observed_revision = self._observed_revision()
        brief = self.catalog.get("mission/brief")
        if brief is None:
            return DesignApprovalResult(
                ApplyStatus.REJECTED,
                store.current_revision(),
                observed_revision,
                detail="reviewed brief is required before design approval",
            )
        if base_brief_revision is not None and base_brief_revision != brief.revision:
            return DesignApprovalResult(
                ApplyStatus.CONFLICT,
                store.current_revision(),
                observed_revision,
                brief_revision=brief.revision,
                detail=(
                    f"brief revision conflict; base {base_brief_revision} "
                    f"!= current {brief.revision}"
                ),
            )
        base_commit = self.git.current_commit()
        result = store.approve(
            base_revision=base_revision,
            observed_revision=observed_revision,
            metadata={
                "brief": {
                    "logical_id": brief.logical_id,
                    "revision": brief.revision,
                },
                "project": {
                    "name": self.project_name,
                    "path": str(self.project_dir),
                },
                "base_commit": base_commit,
            },
        )
        if result.status is not ApplyStatus.APPLIED or result.snapshot is None:
            return DesignApprovalResult(
                result.status,
                store.current_revision(),
                observed_revision,
                brief_revision=brief.revision,
                base_commit=base_commit,
                detail=(
                    f"design revision conflict; base {base_revision} "
                    f"!= current {store.current_revision()}"
                ),
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
                "brief_revision": brief.revision,
                "base_commit": base_commit,
            },
        )
        return DesignApprovalResult(
            ApplyStatus.APPLIED,
            int(snapshot["design_revision"]),
            int(snapshot["observed_revision"]),
            str(snapshot["snapshot_id"]),
            brief.revision,
            base_commit,
        )

    def _observed_revision(self) -> int:
        facts_path = self.harness_dir / "code_graph.db"
        if not facts_path.exists():
            return 0
        return SQLiteCodeGraph(facts_path).observed_revision()
