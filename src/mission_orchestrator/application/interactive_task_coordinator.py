from __future__ import annotations

import threading

from mission_orchestrator.application.burst_executor import BurstExecutor
from mission_orchestrator.application.context_compactor import ContextCompactor
from mission_orchestrator.application.contract_execution import ContractExecutionService
from mission_orchestrator.application.document_service import MissionDocumentService
from mission_orchestrator.application.phase_executor import PhaseExecutor
from mission_orchestrator.application.pipeline_definitions import mode_should_merge, task_pipeline_for
from mission_orchestrator.application.preparation_coordinator import (
    InvalidSessionAction,
    PreparationResult,
)
from mission_orchestrator.application.reconciler import Reconciler
from mission_orchestrator.application.report_service import ReportService
from mission_orchestrator.application.task_contracts import (
    TASK_CONTRACT_ALIAS,
    TASK_CONTRACT_INDEX,
    TaskContractCompiler,
)
from mission_orchestrator.application.review_coordinator import ReviewCoordinator
from mission_orchestrator.application.services import AppServices
from mission_orchestrator.domain.mission import MissionContext, MissionMode, MissionSnapshot
from mission_orchestrator.domain.phase import PhaseName
from mission_orchestrator.domain.session import MissionSession, MissionStage
from mission_orchestrator.domain.task import Task, TaskStatus
from mission_orchestrator.domain.workplan import dependency_block_reason, next_runnable_index
from mission_orchestrator.ports.session_store import MissionSessionStore, SessionConflictError


PREPARATION_PHASES = frozenset({PhaseName.SPEC, PhaseName.PLAN})
STALE_TASK_ALIASES = (
    "spec.md",
    "plan.md",
    "decisions.md",
    "status.md",
    "audit.md",
    "contract-verification.json",
    "reconciliation.json",
    "_burst_progress.md",
    TASK_CONTRACT_ALIAS,
)


class InteractiveTaskCoordinator:
    def __init__(
        self,
        *,
        services: AppServices,
        context: MissionContext,
        sessions: MissionSessionStore,
        documents: MissionDocumentService,
    ) -> None:
        self.services = services
        self.context = context
        self.sessions = sessions
        self.documents = documents
        self.phases = PhaseExecutor(services, context)
        self.compactor = ContextCompactor(self.phases)
        self.review = ReviewCoordinator(services, context, self.phases, self.compactor)
        self.bursts = BurstExecutor(self.phases)
        self.reporter = ReportService(self.phases, context)
        self.executions = ContractExecutionService(
            services=services,
            context=context,
            sessions=sessions,
        )
        self._action_lock = threading.Lock()

    def prepare_next(self, *, expected_session_revision: int) -> PreparationResult:
        with self._action_lock:
            current = self._expected(expected_session_revision, MissionStage.READY, "prepare_task")
            tasks = self.services.tasks.load()
            index = next_runnable_index(tasks)
            if index is None:
                return self._finish_or_block(current, tasks)
            task = tasks[index]
            running = current.move_to(
                MissionStage.TASK_PREPARATION,
                active_phase="task_preparation",
                active_task_id=task.id,
            )
            self._save(current, running)
            self._clear_aliases()
            self._materialize_task_contract(task.id)
            self.services.code_graph.build(self.context.project_dir)
            self.services.state.update_phase(
                MissionSnapshot(
                    phase="task_preparation",
                    task_id=task.id,
                    task_title=task.title,
                    task_num=index + 1,
                    task_count=len(tasks),
                    completed=sum(item.status is TaskStatus.COMPLETED for item in tasks),
                    mode=self.context.mode.value,
                    gate=self.services.state.get_gate_mode().value,
                )
            )
            for phase in task_pipeline_for(task, self.context.mode).phases:
                if phase not in PREPARATION_PHASES:
                    continue
                execution = self.phases.run(
                    phase,
                    variables={"TASK_ID": task.id, "TASK_TITLE": task.title},
                )
                if phase is PhaseName.PLAN and not self.services.artifacts.exists("decisions.md"):
                    self.services.artifacts.write_text(
                        "decisions.md",
                        "# Decisions\n\n(not available yet)\n",
                    )
                self.documents.capture_task_documents(task.id)
                if execution.block is not None:
                    return self._block(running, str(execution.block))
            review = running.move_to(
                MissionStage.TASK_REVIEW,
                active_phase="task_review",
                active_task_id=task.id,
            )
            self._save(running, review)
            self.services.events.publish(
                "task_prepared",
                {"task_id": task.id, "task_title": task.title},
            )
            return PreparationResult(review)

    def execute_prepared(
        self,
        *,
        expected_session_revision: int,
        task_id: str,
    ) -> PreparationResult:
        with self._action_lock:
            current = self._expected(
                expected_session_revision,
                MissionStage.TASK_REVIEW,
                "approve_task",
            )
            if current.active_task_id != task_id:
                raise ValueError(
                    f"active task is {current.active_task_id!r}, not requested task {task_id!r}"
                )
            tasks = self.services.tasks.load()
            index, task = self._find_task(tasks, task_id)
            execution_id = ""
            if (
                self.context.mode is not MissionMode.PLAN
                and self.services.artifacts.exists(TASK_CONTRACT_INDEX)
            ):
                lease = self.executions.begin(task_id=task.id, actor="mission")
                execution_id = str(lease["execution_id"])
            try:
                self._materialize_task_contract(task.id)
                running = current.move_to(
                    MissionStage.EXECUTING,
                    active_phase="execute",
                    active_task_id=task.id,
                )
                self._save(current, running)
                for phase in task_pipeline_for(task, self.context.mode).phases:
                    if phase in PREPARATION_PHASES:
                        continue
                    if phase is PhaseName.IMPLEMENT_BURSTS:
                        block = self.bursts.run(task)
                    else:
                        block = self.phases.run(
                            phase,
                            variables={"TASK_ID": task.id, "TASK_TITLE": task.title},
                        ).block
                    self.documents.capture_task_documents(task.id)
                    if block is not None:
                        self.services.tasks.update(index, TaskStatus.FAILED, str(block))
                        if execution_id:
                            self.executions.report_blocker(execution_id, str(block))
                        return self._block(running, str(block))
                    if self._amendment_requested():
                        if execution_id:
                            self.executions.propose_amendment(
                                execution_id,
                                "Mission execution requested a design amendment",
                            )
                        return self._pause_for_amendment(running)
                result = self._finish_execution(running, index, task)
                if execution_id:
                    self._close_mission_execution(execution_id, result)
                return result
            except Exception as error:
                if execution_id:
                    self._safe_execution_blocker(execution_id, str(error))
                raise

    def retry_review(self, *, expected_session_revision: int) -> PreparationResult:
        with self._action_lock:
            current = self._expected(expected_session_revision, MissionStage.BLOCKED, "retry")
            if "phase=review" not in current.blocked_reason:
                raise InvalidSessionAction(current.stage, "retry_review")
            tasks = self.services.tasks.load()
            index, task = self._find_task(tasks, current.active_task_id)
            execution_id = ""
            if self.services.artifacts.exists(TASK_CONTRACT_INDEX):
                lease = self.executions.begin(task_id=task.id, actor="mission")
                execution_id = str(lease["execution_id"])
            self._materialize_task_contract(task.id)
            if task.status is not TaskStatus.FAILED:
                raise ValueError(f"active task {task.id!r} is not failed")
            running = current.move_to(
                MissionStage.EXECUTING,
                active_phase="review",
                active_task_id=task.id,
            )
            self._save(current, running)
            self.services.tasks.update(index, TaskStatus.PENDING)
            block = self.phases.run(
                PhaseName.REVIEW,
                variables={"TASK_ID": task.id, "TASK_TITLE": task.title},
            ).block
            self.documents.capture_task_documents(task.id)
            if block is not None:
                self.services.tasks.update(index, TaskStatus.FAILED, str(block))
                if execution_id:
                    self.executions.report_blocker(execution_id, str(block))
                return self._block(running, str(block))
            result = self._finish_execution(running, index, task)
            if execution_id:
                self._close_mission_execution(execution_id, result)
            return result

    def _close_mission_execution(
        self,
        execution_id: str,
        result: PreparationResult,
    ) -> None:
        if result.session.stage is MissionStage.PAUSED:
            self.executions.propose_amendment(
                execution_id,
                result.detail or "Mission execution requested a design amendment",
            )
        elif result.session.stage is MissionStage.BLOCKED:
            self.executions.report_blocker(
                execution_id,
                result.detail or result.session.blocked_reason or "Mission execution blocked",
            )
        else:
            self.executions.complete(execution_id, manage_workflow=False)

    def _safe_execution_blocker(self, execution_id: str, detail: str) -> None:
        try:
            current = self.executions.current_execution()
            if current and current.get("execution_id") == execution_id and current.get("status") == "active":
                self.executions.report_blocker(execution_id, detail or "Mission execution failed")
        except Exception:
            return

    def _finish_execution(
        self,
        running: MissionSession,
        index: int,
        task: Task,
    ) -> PreparationResult:
            pipeline = task_pipeline_for(task, self.context.mode)
            if self.context.mode is MissionMode.PLAN:
                self.services.tasks.update(index, TaskStatus.COMPLETED)
                self.compactor.compact(task.id)
            elif PhaseName.REVIEW in pipeline.phases:
                block = self.review.commit_or_request_human(index, task)
                self.documents.capture_task_documents(task.id)
                if block is not None:
                    self.services.tasks.update(index, TaskStatus.FAILED, str(block))
                    return self._block(running, str(block))
            else:
                block = self.review.approve_without_review(index, task)
                self.documents.capture_task_documents(task.id)
                if block is not None:
                    self.services.tasks.update(index, TaskStatus.FAILED, str(block))
                    return self._block(running, str(block))
            if self._amendment_requested():
                return self._pause_for_amendment(running)
            reconciling = running.move_to(
                MissionStage.RECONCILING,
                active_phase="reconcile",
                active_task_id=task.id,
            )
            self._save(running, reconciling)
            self.services.code_graph.build(self.context.project_dir)
            refreshed = self.services.tasks.load()
            _, reasons = Reconciler(
                self.context.harness_dir,
                self.services.artifacts,
            ).evaluate(refreshed)
            self.documents.capture_task_documents(task.id)
            if self._amendment_requested():
                return self._pause_for_amendment(reconciling)
            if any(item.status is TaskStatus.PENDING for item in refreshed):
                next_session = reconciling.move_to(
                    MissionStage.READY,
                    active_task_id="",
                )
            else:
                result = self.reporter.generate_report(
                    completed=sum(item.status is TaskStatus.COMPLETED for item in refreshed),
                    block=None,
                )
                self.documents.capture_mission_document(
                    "mission/report",
                    author="AGENT",
                    phase="report",
                )
                if self._amendment_requested():
                    return self._pause_for_amendment(reconciling)
                if reasons:
                    return self._block(reconciling, "; ".join(reasons))
                self._commit_and_merge(result.summary)
                self.services.events.publish(
                    "mission_finalized",
                    {
                        "outcome": result.outcome.value,
                        "completed": result.completed,
                        "failed": result.failed,
                    },
                )
                next_session = reconciling.move_to(
                    MissionStage.COMPLETED,
                    active_task_id="",
                )
            self._save(reconciling, next_session)
            self.services.events.publish(
                "task_completed",
                {"task_id": task.id, "task_title": task.title},
            )
            return PreparationResult(next_session)

    def _expected(
        self,
        expected_revision: int,
        stage: MissionStage,
        action: str,
    ) -> MissionSession:
        current = self.sessions.load(self.context.mission_tag)
        if current.revision != expected_revision:
            raise SessionConflictError(current.revision)
        if current.stage is not stage:
            raise InvalidSessionAction(current.stage, action)
        return current

    def _save(self, previous: MissionSession, updated: MissionSession) -> None:
        self.sessions.save(updated, expected_revision=previous.revision)
        self.services.events.publish(
            "session_updated",
            {
                "mission_id": updated.mission_id,
                "revision": updated.revision,
                "stage": updated.stage.value,
                "active_phase": updated.active_phase,
                "active_task_id": updated.active_task_id,
            },
        )

    def _block(self, running: MissionSession, detail: str) -> PreparationResult:
        blocked = running.move_to(MissionStage.BLOCKED, blocked_reason=detail)
        self._save(running, blocked)
        return PreparationResult(blocked, False, detail)

    def _finish_or_block(
        self,
        current: MissionSession,
        tasks: list[Task],
    ) -> PreparationResult:
        if tasks and all(task.status is TaskStatus.COMPLETED for task in tasks):
            completed = current.move_to(MissionStage.COMPLETED)
            self._save(current, completed)
            return PreparationResult(completed)
        by_id = {task.id: task for task in tasks}
        detail = "; ".join(
            f"{task.id}: {dependency_block_reason(task, by_id) or 'not runnable'}"
            for task in tasks
            if task.status is TaskStatus.PENDING
        ) or "no runnable task"
        return self._block(current, detail)

    @staticmethod
    def _find_task(tasks: list[Task], task_id: str) -> tuple[int, Task]:
        for index, task in enumerate(tasks):
            if task.id == task_id:
                return index, task
        raise ValueError(f"unknown task: {task_id}")

    def _clear_aliases(self) -> None:
        for alias in STALE_TASK_ALIASES:
            self.services.artifacts.delete(alias)

    def _materialize_task_contract(self, task_id: str) -> None:
        if self.services.artifacts.exists(TASK_CONTRACT_INDEX):
            TaskContractCompiler(self.services.artifacts).materialize(task_id)

    def _amendment_requested(self) -> bool:
        return self.services.artifacts.exists("_amendment_pending.json")

    def _pause_for_amendment(self, current: MissionSession) -> PreparationResult:
        paused = current.move_to(
            MissionStage.PAUSED,
            active_phase="amendment_pending",
        )
        self._save(current, paused)
        review = paused.move_to(
            MissionStage.AMENDMENT_REVIEW,
            active_phase="amendment_review",
        )
        self._save(paused, review)
        self.services.artifacts.delete("_amendment_pending.json")
        self.services.events.publish(
            "execution_paused_for_amendment",
            {"task_id": review.active_task_id, "session_revision": review.revision},
        )
        return PreparationResult(review, detail="execution paused for design amendment")

    def _commit_and_merge(self, summary: str) -> None:
        if not mode_should_merge(self.context.mode):
            return
        try:
            self.services.git.final_commit(self.context.task, summary)
            merged = self.services.git.merge_to_develop(self.context.branch)
        except Exception as error:
            self.services.notifier.notify(f"Merge failed: {error}")
            return
        if merged:
            self.services.notifier.notify(
                f"Merge successful: {self.context.branch} -> develop"
            )
        else:
            self.services.notifier.notify("Merge skipped or failed validation.")
