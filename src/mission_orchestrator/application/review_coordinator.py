from __future__ import annotations

import json
from pathlib import Path

from mission_orchestrator.application.context_compactor import ContextCompactor
from mission_orchestrator.application.contract_verifier import PythonContractVerifier
from mission_orchestrator.application.markdown_contracts import (
    ReviewVerdict,
    audit_verdict,
    status_files,
)
from mission_orchestrator.application.phase_executor import PhaseExecutor
from mission_orchestrator.application.services import AppServices
from mission_orchestrator.domain.block import BlockKind, BlockReason
from mission_orchestrator.domain.command import CommandKind
from mission_orchestrator.domain.mission import GateMode, MissionContext, WaitingApproval
from mission_orchestrator.domain.phase import PhaseName
from mission_orchestrator.domain.task import Task, TaskStatus


class ReviewCoordinator:
    def __init__(
        self,
        services: AppServices,
        context: MissionContext,
        phase_executor: PhaseExecutor,
        compactor: ContextCompactor,
    ) -> None:
        self.services = services
        self.context = context
        self.phase_executor = phase_executor
        self.compactor = compactor
        self._verdict_attempts: dict[str, int] = {}

    def commit_or_request_human(self, index: int, task: Task) -> BlockReason | None:
        verdict = self.current_verdict()
        self._record_verdict(task, verdict)
        if verdict == ReviewVerdict.APPROVED:
            if self.services.state.get_gate_mode() == GateMode.MANUAL:
                decision = self._wait_manual_approval(task)
                if decision:
                    return decision
            return self.complete_task(index, task)
        if verdict == ReviewVerdict.MINOR_CHANGES:
            self.services.notifier.notify(f"Task {task.id} has minor changes; reimplementing.")
            self.services.logger.metric({"event": "rework", "task_id": task.id, "cause": "minor_changes"})
            block = self.phase_executor.run(
                PhaseName.REIMPLEMENT,
                variables={"TASK_ID": task.id, "TASK_TITLE": task.title},
            ).block
            if block:
                return block
            return self.complete_task(index, task)
        return self._review_loop(index, task, verdict)

    def approve_without_review(self, index: int, task: Task) -> BlockReason | None:
        return self.complete_task(index, task)

    def _record_verdict(self, task: Task, verdict: str) -> None:
        self._verdict_attempts[task.id] = self._verdict_attempts.get(task.id, 0) + 1
        self.services.logger.metric(
            {
                "event": "review_verdict",
                "task_id": task.id,
                "verdict": verdict,
                "attempt": self._verdict_attempts[task.id],
            }
        )

    def current_verdict(self) -> str:
        return audit_verdict(self.services.artifacts.read_text("audit.md", default=""))

    def complete_task(self, index: int, task: Task) -> BlockReason | None:
        verification = self._verify_contract()
        if verification is not None:
            return verification
        self.services.notifier.notify(f"Task approved: {task.id} {task.title}")
        self._stage_status_files()
        self.services.tasks.update(index, TaskStatus.COMPLETED)
        self.compactor.compact(task.id)
        return None

    def _verify_contract(self) -> BlockReason | None:
        raw = self.services.artifacts.read_text("task-contract.json", default="")
        if not raw:
            return None
        try:
            contract = json.loads(raw)
        except json.JSONDecodeError as error:
            return BlockReason(BlockKind.GATE_FAIL, "contract_verification", str(error))
        verification = PythonContractVerifier(self.context.project_dir).verify(contract)
        self.services.artifacts.write_text(
            "contract-verification.json",
            verification.to_json() + "\n",
        )
        failed = [check for check in verification.checks if check.state.value == "failed"]
        self.services.logger.metric(
            {
                "event": "contract_verification",
                "snapshot_id": verification.snapshot_id,
                "task_id": verification.task_id,
                "passed": verification.passed,
                "failed_checks": len(failed),
            }
        )
        if verification.passed:
            return None
        detail = "; ".join(
            f"{check.node_id}.{check.field}: {check.detail}" for check in failed
        )
        return BlockReason(BlockKind.GATE_FAIL, "contract_verification", detail)

    def _stage_status_files(self) -> None:
        text = self.services.artifacts.read_text("status.md", default="")
        files: list[Path] = []
        for path in status_files(text):
            full_path = path if path.is_absolute() else self.context.project_dir / path
            if full_path.exists():
                files.append(full_path)
        self.services.git.stage_files(files)

    def _wait_manual_approval(self, task: Task) -> BlockReason | None:
        self.services.state.set_waiting_approval(
            WaitingApproval(task.id, task.title, ReviewVerdict.APPROVED)
        )
        self.services.notifier.notify(
            f"Task {task.id} is approved. Waiting for /approve, /reject, /retry, /skip or /abort."
        )
        while True:
            command = self.services.commands.get(timeout_seconds=5.0)
            if command is None:
                continue
            if command.kind == CommandKind.APPROVE:
                self.services.state.set_waiting_approval(None)
                return None
            if command.kind == CommandKind.REJECT:
                self.services.state.set_waiting_approval(None)
                return BlockReason(BlockKind.USER_REJECTED, "review", command.reason or "rejected")
            if command.kind == CommandKind.RETRY:
                self.services.state.set_waiting_approval(None)
                return self._retry(task, command.feedback)
            if command.kind == CommandKind.SKIP:
                self.services.state.set_waiting_approval(None)
                return BlockReason(BlockKind.USER_REJECTED, "review", command.reason or "skipped")
            if command.kind == CommandKind.ABORT:
                self.services.state.set_waiting_approval(None)
                return BlockReason(BlockKind.USER_ABORT, "review", command.reason or "aborted")
            if command.kind == CommandKind.GATE and command.gate_mode is not None:
                self.services.state.set_gate_mode(command.gate_mode)

    def _review_loop(self, index: int, task: Task, verdict: str) -> BlockReason | None:
        while True:
            self.services.state.set_waiting_approval(WaitingApproval(task.id, task.title, verdict))
            self.services.notifier.notify(
                f"Review for {task.id}: {verdict}. Send /retry feedback, /approve, /skip or /abort."
            )
            command = self.services.commands.get(timeout_seconds=5.0)
            if command is None:
                continue
            if command.kind == CommandKind.RETRY:
                block = self._retry(task, command.feedback)
                if block:
                    self.services.state.set_waiting_approval(None)
                    return block
                verdict = self.current_verdict()
                if verdict == ReviewVerdict.APPROVED:
                    self.services.state.set_waiting_approval(None)
                    return self.complete_task(index, task)
                if verdict == ReviewVerdict.MINOR_CHANGES:
                    self.services.state.set_waiting_approval(None)
                    return self.commit_or_request_human(index, task)
                continue
            if command.kind == CommandKind.APPROVE:
                self.services.state.set_waiting_approval(None)
                return self.complete_task(index, task)
            if command.kind in {CommandKind.SKIP, CommandKind.REJECT}:
                self.services.state.set_waiting_approval(None)
                return BlockReason(
                    BlockKind.USER_REJECTED,
                    "review",
                    command.reason or "review rejected/skipped",
                )
            if command.kind == CommandKind.ABORT:
                self.services.state.set_waiting_approval(None)
                return BlockReason(BlockKind.USER_ABORT, "review", command.reason or "aborted")
            if command.kind == CommandKind.PAUSE:
                self.services.notifier.notify("Review paused. Send /resume or /abort.")
                self._wait_resume_or_abort()
            if command.kind == CommandKind.GATE and command.gate_mode is not None:
                self.services.state.set_gate_mode(command.gate_mode)

    def _retry(self, task: Task, feedback: str) -> BlockReason | None:
        self.services.notifier.notify(f"Retrying task {task.id}.")
        self.services.logger.metric({"event": "rework", "task_id": task.id, "cause": "human_retry"})
        block = self.phase_executor.run(
            PhaseName.REIMPLEMENT,
            variables={"TASK_ID": task.id, "TASK_TITLE": task.title, "REVIEW_FEEDBACK": feedback},
        ).block
        if block:
            return block
        return self.phase_executor.run(
            PhaseName.REVIEW,
            variables={"TASK_ID": task.id, "TASK_TITLE": task.title},
        ).block

    def _wait_resume_or_abort(self) -> BlockReason | None:
        while True:
            command = self.services.commands.get(timeout_seconds=5.0)
            if command is None:
                continue
            if command.kind == CommandKind.RESUME:
                return None
            if command.kind == CommandKind.ABORT:
                return BlockReason(BlockKind.USER_ABORT, "review", command.reason or "aborted")
