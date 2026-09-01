from __future__ import annotations

from mission_orchestrator.application.markdown_contracts import report_preview
from mission_orchestrator.application.phase_executor import PhaseExecutor
from mission_orchestrator.domain.block import BlockReason
from mission_orchestrator.domain.mission import MissionContext, MissionMode
from mission_orchestrator.domain.phase import PhaseName
from mission_orchestrator.domain.result import MissionOutcome, MissionResult
from mission_orchestrator.domain.task import TaskStatus


class ReportService:
    def __init__(self, phase_executor: PhaseExecutor, context: MissionContext) -> None:
        self.phase_executor = phase_executor
        self.context = context

    @property
    def services(self):
        return self.phase_executor.services

    def consolidate_tasks(self, max_tasks: int) -> None:
        artifacts = self.services.artifacts
        tasks = self.services.tasks.load()
        if len(tasks) <= max_tasks:
            return
        backup = artifacts.read_text("tasks.json")
        artifacts.write_text("_tasks_backup.json", backup)
        outcome = self.phase_executor.run(PhaseName.CONSOLIDATE, evaluate_gate=False)
        if outcome.block:
            artifacts.write_text("tasks.json", backup)
            return
        try:
            new_tasks = self.services.tasks.load()
            if not new_tasks or any(not task.id or not task.title for task in new_tasks):
                raise ValueError("invalid consolidated tasks")
        except Exception:
            artifacts.write_text("tasks.json", backup)
            return
        if len(new_tasks) > max_tasks:
            self.services.logger.log(
                f"warning: consolidated tasks still above max_tasks ({len(new_tasks)} > {max_tasks})"
            )

    def generate_report(self, *, completed: int, block: BlockReason | None) -> MissionResult:
        tasks = self.services.tasks.load() if self.services.artifacts.exists("tasks.json") else []
        failed = sum(1 for task in tasks if task.status == TaskStatus.FAILED)
        phase = (
            PhaseName.REPORT
            if self.context.mode in {MissionMode.FULL, MissionMode.FOCUSED, MissionMode.HOTFIX}
            else PhaseName.REPORT_PLAN
        )
        self.phase_executor.run(
            phase,
            variables={
                "TASK_SUMMARY": self.services.tasks.summary() if tasks else "No task file.",
                "BLOCKED": str(block or ""),
                "COMPLETED": str(completed),
            },
            evaluate_gate=False,
        )
        preview = report_preview(self.services.artifacts.read_text("mission-report.md", default=""))
        if block:
            outcome = MissionOutcome.BLOCKED
        elif failed:
            outcome = MissionOutcome.PARTIAL
        else:
            outcome = MissionOutcome.COMPLETE
        result = MissionResult(
            outcome=outcome,
            summary=self.services.tasks.summary() if tasks else "No tasks.",
            completed=completed,
            failed=failed,
            block=block,
            report_preview=preview,
        )
        self.services.notifier.notify_result(result)
        return result
