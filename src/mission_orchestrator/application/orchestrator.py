from __future__ import annotations

from mission_orchestrator.adapters.design.store import DesignStore
from mission_orchestrator.application.approval import ApprovalCoordinator, ApprovalOutcome
from mission_orchestrator.application.context_compactor import ContextCompactor
from mission_orchestrator.application.phase_executor import PhaseExecutor
from mission_orchestrator.application.pipeline_definitions import mission_pipeline_for, mode_should_merge
from mission_orchestrator.application.plan_compiler import PlanCompiler
from mission_orchestrator.application.reconciler import Reconciler
from mission_orchestrator.application.report_service import ReportService
from mission_orchestrator.application.services import AppServices
from mission_orchestrator.application.signal_controller import SignalController
from mission_orchestrator.application.task_executor import TaskExecutor
from mission_orchestrator.domain.block import BlockKind, BlockReason
from mission_orchestrator.domain.mission import MissionContext, MissionMode
from mission_orchestrator.domain.phase import PhaseName
from mission_orchestrator.domain.result import MissionResult
from mission_orchestrator.domain.workplan import validate_plan


class MissionOrchestrator:
    def __init__(self, services: AppServices, context: MissionContext) -> None:
        self.services = services
        self.context = context
        self.phase_executor = PhaseExecutor(services, context)
        self.compactor = ContextCompactor(self.phase_executor)
        self.signals = SignalController(services)
        self.reporter = ReportService(self.phase_executor, context)
        self.block: BlockReason | None = None

    def run(self) -> MissionResult:
        self.services.logger.log(f"mission start: {self.context.mission_tag}")
        if self.context.resume and self.services.artifacts.exists("tasks.json"):
            self.services.notifier.notify(f"Mission resumed: {self.context.mission_tag}")
        else:
            self.services.notifier.notify(f"Mission started: {self.context.mission_tag}")
            if not self._run_init_pipeline():
                return self._finalize(completed=0)

        if self.context.mode == MissionMode.EXPLORE:
            return self._finalize(completed=0)

        if not self.services.artifacts.exists("tasks.json"):
            self.block = BlockReason(BlockKind.STRUCTURE, "structure", "tasks.json missing")
            return self._finalize(completed=0)

        try:
            tasks = self.services.tasks.load()
        except Exception as exc:
            self.block = BlockReason(BlockKind.STRUCTURE, "structure", str(exc))
            return self._finalize(completed=0)
        if not tasks:
            self.block = BlockReason(BlockKind.STRUCTURE, "structure", "tasks.json is empty")
            return self._finalize(completed=0)

        if (
            not self.context.resume
            and len(tasks) > self.context.max_tasks
            and not self.services.artifacts.exists("changeset.json")
        ):
            self.reporter.consolidate_tasks(self.context.max_tasks)
            tasks = self.services.tasks.load()

        task_executor = TaskExecutor(
            self.services,
            self.context,
            self.phase_executor,
            self.signals,
            self.compactor,
        )
        completed = task_executor.run(tasks)
        self.block = task_executor.block
        return self._finalize(completed=completed)

    def _run_init_pipeline(self) -> bool:
        pipeline = mission_pipeline_for(self.context.mode, no_grill=self.context.no_grill)
        if pipeline.init:
            self.services.code_graph.build(self.context.project_dir)
        for phase in pipeline.init:
            if phase == PhaseName.STRUCTURE and not self._approve_and_compile_map():
                return False
            if phase == PhaseName.COMPACT:
                self.block = self.compactor.compact("init")
            else:
                self.block = self.phase_executor.run(phase).block
            if self.block:
                return False
            if phase == PhaseName.STRUCTURE and not self._validate_structure():
                return False
            if not self.signals.check_signals():
                self.block = self.signals.block
                return False
        return True

    def _design_store(self) -> DesignStore:
        return DesignStore(self.context.harness_dir / "design.db")

    def _approve_and_compile_map(self) -> bool:
        store = self._design_store()
        if not store.nodes():
            return True
        scope = self.context.project_scope_dir or (self.context.harness_dir / "project_scope")
        facts_path = self.context.harness_dir / "code_graph.db"
        observed_revision = 0
        if facts_path.exists():
            from mission_orchestrator.adapters.analysis.sqlite_graph import SQLiteCodeGraph

            observed_revision = SQLiteCodeGraph(facts_path).observed_revision()
        decision = ApprovalCoordinator(
            store=store,
            commands=self.services.commands,
            notifier=self.services.notifier,
            harness_dir=self.context.harness_dir,
            project_scope_dir=scope,
            observed_revision=observed_revision,
        ).wait_for_approval()
        if decision.kind == ApprovalOutcome.ABORTED:
            self.block = BlockReason(BlockKind.USER_ABORT, "approval", decision.reason)
            return False
        if decision.kind == ApprovalOutcome.REJECTED:
            self.block = BlockReason(BlockKind.USER_REJECTED, "approval", decision.reason)
            return False
        changeset = PlanCompiler(self.context.harness_dir, self.services.artifacts).compile()
        if changeset and changeset.issues:
            details = "; ".join(issue.detail for issue in changeset.issues)
            self.services.notifier.notify(f"Changeset compiled with issues: {details}")
        return True

    def _validate_structure(self) -> bool:
        try:
            tasks = self.services.tasks.load()
        except Exception as exc:
            self.block = BlockReason(BlockKind.STRUCTURE, "structure", str(exc))
            return False
        if not tasks:
            self.block = BlockReason(BlockKind.STRUCTURE, "structure", "tasks.json is empty")
            return False
        raw = self.services.artifacts.read_text("changeset.json", default="")
        if raw:
            import json

            operation_ids = [op["id"] for op in json.loads(raw).get("operations", [])]
            errors = validate_plan(operation_ids, tasks)
            if errors:
                self.block = BlockReason(BlockKind.STRUCTURE, "structure", "; ".join(errors))
                return False
        return True

    def _finalize(self, *, completed: int) -> MissionResult:
        result = self.reporter.generate_report(completed=completed, block=self.block)
        if self.block is None and mode_should_merge(self.context.mode):
            gate_reasons = self._reconciliation_gate()
            if gate_reasons:
                self.services.notifier.notify(
                    "Merge gate blocked automatic merge: " + "; ".join(gate_reasons)
                )
            else:
                self._commit_and_merge(result)
        self.services.logger.log(f"mission result: {result.outcome.value}")
        return result

    def _reconciliation_gate(self) -> list[str]:
        if not self.services.artifacts.exists("changeset.json"):
            return []
        self.services.code_graph.build(self.context.project_dir)
        try:
            tasks = self.services.tasks.load()
        except Exception:
            tasks = []
        return Reconciler(self.context.harness_dir, self.services.artifacts).gate_reasons(tasks)

    def _commit_and_merge(self, result: MissionResult) -> None:
        try:
            self.services.git.final_commit(self.context.task, result.summary)
            merged = self.services.git.merge_to_develop(self.context.branch)
        except Exception as exc:
            self.services.notifier.notify(f"Merge failed: {exc}")
            return
        if merged:
            self.services.notifier.notify(f"Merge successful: {self.context.branch} -> develop")
        else:
            self.services.notifier.notify("Merge skipped or failed validation.")

