from __future__ import annotations

from mission_orchestrator.application.burst_executor import BurstExecutor
from mission_orchestrator.application.context_compactor import ContextCompactor
from mission_orchestrator.application.pipeline_definitions import task_pipeline_for
from mission_orchestrator.application.review_coordinator import ReviewCoordinator
from mission_orchestrator.application.services import AppServices
from mission_orchestrator.application.signal_controller import SignalController
from mission_orchestrator.application.task_contracts import (
    TASK_CONTRACT_ALIAS,
    TASK_CONTRACT_INDEX,
    TaskContractCompiler,
)
from mission_orchestrator.domain.block import BlockReason
from mission_orchestrator.domain.mission import MissionContext, MissionMode, MissionSnapshot
from mission_orchestrator.domain.phase import PhaseName
from mission_orchestrator.domain.task import Task, TaskStatus
from mission_orchestrator.domain.workplan import dependency_block_reason, next_runnable_index


STALE_TASK_ARTIFACTS = (
    "spec.md",
    "plan.md",
    "decisions.md",
    "status.md",
    "audit.md",
    "review-evidence.json",
    "review-receipt.json",
    "contract-verification.json",
    "_burst_progress.md",
    TASK_CONTRACT_ALIAS,
)


class TaskExecutor:
    def __init__(
        self,
        services: AppServices,
        context: MissionContext,
        phase_executor,
        signal_controller: SignalController,
        compactor: ContextCompactor,
    ) -> None:
        self.services = services
        self.context = context
        self.phase_executor = phase_executor
        self.signal_controller = signal_controller
        self.compactor = compactor
        self.burst_executor = BurstExecutor(phase_executor)
        self.review = ReviewCoordinator(services, context, phase_executor, compactor)
        self.block: BlockReason | None = None

    def run(self, tasks: list[Task]) -> int:
        completed = sum(1 for task in tasks if task.status == TaskStatus.COMPLETED)
        total = len(tasks)
        while True:
            if not self.signal_controller.check_signals():
                self.block = self.signal_controller.block
                break
            index = next_runnable_index(tasks)
            if index is None:
                self._block_unrunnable(tasks)
                break
            task = tasks[index]
            self._clear_stale_task_artifacts()
            self._materialize_task_contract(task.id)
            self.services.code_graph.build(self.context.project_dir)
            self.services.state.update_phase(
                MissionSnapshot(
                    phase="task",
                    task_id=task.id,
                    task_title=task.title,
                    task_num=index + 1,
                    task_count=total,
                    completed=completed,
                    mode=self.context.mode.value,
                    gate=self.services.state.get_gate_mode().value,
                )
            )
            block = self._run_task_pipeline(task)
            if block:
                if block.is_mission_abort:
                    self.block = block
                    break
                self._mark(tasks, index, TaskStatus.FAILED, str(block))
                continue
            if self.context.mode == MissionMode.PLAN:
                self._mark(tasks, index, TaskStatus.COMPLETED)
                self.compactor.compact(task.id)
                completed += 1
                continue
            pipeline = task_pipeline_for(task, self.context.mode)
            if PhaseName.REVIEW in pipeline.phases:
                block = self.review.commit_or_request_human(index, task)
            else:
                block = self.review.approve_without_review(index, task)
            if block:
                if block.is_mission_abort:
                    self.block = block
                    break
                self._mark(tasks, index, TaskStatus.FAILED, str(block))
                continue
            task.status = TaskStatus.COMPLETED
            completed += 1
        return completed

    def _mark(self, tasks: list[Task], index: int, status: TaskStatus, reason: str = "") -> None:
        self.services.tasks.update(index, status, reason)
        tasks[index].status = status
        tasks[index].failure_reason = reason

    def _block_unrunnable(self, tasks: list[Task]) -> None:
        by_id = {task.id: task for task in tasks}
        for index, task in enumerate(tasks):
            if task.status != TaskStatus.PENDING:
                continue
            reason = dependency_block_reason(task, by_id) or "unresolvable dependencies"
            self._mark(tasks, index, TaskStatus.BLOCKED, reason)

    def _run_task_pipeline(self, task: Task) -> BlockReason | None:
        pipeline = task_pipeline_for(task, self.context.mode)
        for phase in pipeline.phases:
            if not self.signal_controller.check_signals():
                return self.signal_controller.block
            if phase == PhaseName.IMPLEMENT_BURSTS:
                block = self.burst_executor.run(task)
            else:
                block = self.phase_executor.run(
                    phase,
                    variables={"TASK_ID": task.id, "TASK_TITLE": task.title},
                    complexity=task.complexity.value,
                ).block
            if phase == PhaseName.PLAN and not self.services.artifacts.exists("decisions.md"):
                self.services.artifacts.write_text("decisions.md", "# Decisions\n\n(not available yet)\n")
            if block:
                return block
        return None

    def _clear_stale_task_artifacts(self) -> None:
        for artifact in STALE_TASK_ARTIFACTS:
            self.services.artifacts.delete(artifact)

    def _materialize_task_contract(self, task_id: str) -> None:
        if self.services.artifacts.exists(TASK_CONTRACT_INDEX):
            TaskContractCompiler(self.services.artifacts).materialize(task_id)
