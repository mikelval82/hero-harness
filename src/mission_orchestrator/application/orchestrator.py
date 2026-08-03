from __future__ import annotations

from mission_orchestrator.application.context_compactor import ContextCompactor
from mission_orchestrator.application.phase_executor import PhaseExecutor
from mission_orchestrator.application.pipeline_definitions import mission_pipeline_for, mode_should_merge
from mission_orchestrator.application.report_service import ReportService
from mission_orchestrator.application.services import AppServices
from mission_orchestrator.application.signal_controller import SignalController
from mission_orchestrator.application.task_executor import TaskExecutor
from mission_orchestrator.domain.block import BlockKind, BlockReason
from mission_orchestrator.domain.mission import MissionContext, MissionMode
from mission_orchestrator.domain.phase import PhaseName
from mission_orchestrator.domain.result import MissionResult


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

        if not self.context.resume and len(tasks) > self.context.max_tasks:
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

    def _validate_structure(self) -> bool:
        try:
            tasks = self.services.tasks.load()
        except Exception as exc:
            self.block = BlockReason(BlockKind.STRUCTURE, "structure", str(exc))
            return False
        if not tasks:
            self.block = BlockReason(BlockKind.STRUCTURE, "structure", "tasks.json is empty")
            return False
        return True

    def _finalize(self, *, completed: int) -> MissionResult:
        result = self.reporter.generate_report(completed=completed, block=self.block)
        if self.block is None and mode_should_merge(self.context.mode):
            self._commit_and_merge(result)
        self.services.logger.log(f"mission result: {result.outcome.value}")
        return result

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

