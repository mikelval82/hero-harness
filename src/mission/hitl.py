from __future__ import annotations

import json
import queue
from typing import TYPE_CHECKING, Callable

from src.core.block_state import BlockKind, BlockReason, BlockState
from src.core.notification import notify
from src.core.state import (
    ControlState,
    Interaction,
    InteractionKind,
    MissionStateProtocol,
    _apply_gate_change,
    update_state,
)
from src.core.context import PHASE_REGISTRY, PhaseName, MissionContext
from src.harness.tasks import (
    update_task as _update_task,
    audit_verdict as _audit_verdict,
    stage_task_files,
)
from src.harness.telemetry import write_intervention
from src.mission.control import CommandEnvelope, coerce_envelope
from src.mission.signals import control_checkpoint

if TYPE_CHECKING:
    from src.mission.phase_runner import PhaseRunner


class HitlReviewer:

    def __init__(
        self,
        ctx: MissionContext,
        phase_runner: PhaseRunner,
        command_queue: queue.Queue,
        mission_state: MissionStateProtocol,
        blocked: BlockState,
        log: Callable[[str], None],
        compact_fn: Callable[..., None],
    ) -> None:
        self.ctx = ctx
        self.phase_runner = phase_runner
        self.command_queue = command_queue
        self.mission_state = mission_state
        self.blocked = blocked
        self.log = log
        self.compact_fn = compact_fn
        self._retry_counts: dict[str, int] = {}

    def commit_task(self, index: int, task_id: str, task_title: str) -> None:
        harness = self.ctx.harness
        if self.blocked.reason:
            _update_task(index, "failed", harness, reason=self.blocked.value)
            return

        verdict = _audit_verdict(harness)
        if verdict == "APPROVED":
            gate_file = harness / "_gate_mode"
            gate = gate_file.read_text(encoding="utf-8").strip() if gate_file.is_file() else "auto"
            if gate == "manual" and not self.wait_approval(task_id, task_title):
                return
            print(f"Task {task_id} APPROVED")
            notify(f"\u2705 Task {task_id} APPROVED")
            stage_task_files(harness)
            _update_task(index, "completed", harness)
            self.compact_fn(task_id=task_id, task_title=task_title)
            return

        if verdict == "MINOR_CHANGES":
            print(f"Task {task_id} MINOR_CHANGES — running fast-path reimplement...")
            notify(f"\U0001f527 Task {task_id} MINOR_CHANGES — fast-path reimplement")
            retry_count = self._increment_retry(task_id)
            self._write_intervention(
                "auto_reimplement",
                task_id,
                task_title,
                source="system",
                verdict=verdict,
                retry_count=retry_count,
            )
            self.run_reimplement(task_id, task_title, "")
            if self.blocked.reason:
                _update_task(index, "failed", harness, reason=self.blocked.value)
                return
            print(f"Task {task_id} APPROVED after fast-path reimplement")
            notify(f"\u2705 Task {task_id} APPROVED after fast-path")
            stage_task_files(harness)
            _update_task(index, "completed", harness)
            self.compact_fn(task_id=task_id, task_title=task_title)
            return

        self.hitl_review_loop(index, task_id, task_title)

    def run_reimplement(self, task_id: str, task_title: str, user_feedback: str) -> bool:
        feedback_block = (
            f"Additional feedback from the user: {user_feedback}"
            if user_feedback
            else "No additional user feedback. Focus on the reviewer's audit."
        )
        self._set_phase(PhaseName.REIMPLEMENT, task_id, task_title)
        self.phase_runner.run(
            PHASE_REGISTRY[PhaseName.REIMPLEMENT],
            {**self._task_variables(task_id, task_title), "USER_FEEDBACK": feedback_block},
            phase_name_override=f"reimplement[{task_id}]",
            log=self.log,
        )
        return self._checkpoint()

    def wait_approval(self, task_id: str, task_title: str) -> bool:
        verdict = _audit_verdict(self.ctx.harness)
        prompt = (
            f"Approve task {task_id} — {task_title}? "
            f"Reviewer verdict: {verdict}. Reply /approve or /reject [reason]."
        )
        self._set_phase("waiting_approval", task_id, task_title)
        interaction = self.mission_state.open_interaction(
            InteractionKind.APPROVAL,
            task_id=task_id,
            prompt=prompt,
        )
        self._write_intervention(
            "waiting_approval",
            task_id,
            task_title,
            source="system",
            verdict=verdict,
        )
        print(f"HITL: {prompt}")
        try:
            while True:
                cmd = self._next_interaction_command(interaction, {"approve", "reject"})
                if cmd.name == "approve":
                    self._write_intervention("approve", task_id, task_title, verdict=verdict)
                    return True
                if cmd.name == "reject":
                    reason = cmd.get("reason", "")
                    self._write_intervention(
                        "reject",
                        task_id,
                        task_title,
                        verdict=verdict,
                        feedback=reason,
                    )
                    self.blocked.reason = BlockReason(
                        BlockKind.USER_REJECTED,
                        phase=task_id,
                        detail=reason,
                    )
                    notify(f"\u274c Task {task_id} REJECTED by user" + (f" — {reason}" if reason else ""))
                    return False
                if cmd.name == "abort":
                    self._write_intervention("abort", task_id, task_title, verdict=verdict)
                    self._abort()
                    return False
        finally:
            self.mission_state.close_interaction(interaction.id)

    def hitl_review_loop(self, index: int, task_id: str, task_title: str) -> None:
        harness = self.ctx.harness
        while True:
            verdict = _audit_verdict(harness)
            prompt = (
                f"Task {task_id} — {task_title}: reviewer returned {verdict}. "
                "Reply /retry [feedback], /skip, or /approve to force approval."
            )
            self._set_phase("waiting_review_decision", task_id, task_title)
            interaction = self.mission_state.open_interaction(
                InteractionKind.REVIEW_DECISION,
                task_id=task_id,
                prompt=prompt,
            )
            self._write_intervention(
                "waiting_review_decision",
                task_id,
                task_title,
                source="system",
                verdict=verdict,
            )
            print(f"HITL: {prompt}")
            try:
                cmd = self._next_interaction_command(
                    interaction,
                    {"retry", "skip", "approve"},
                )
            finally:
                self.mission_state.close_interaction(interaction.id)

            decision = cmd.name
            if decision == "abort":
                self._write_intervention("abort", task_id, task_title, verdict=verdict)
                self._abort()
                _update_task(index, "failed", harness, reason="user_abort")
                return

            if decision == "retry":
                feedback = cmd.get("feedback", "")
                retry_count = self._increment_retry(task_id)
                self._write_intervention(
                    "retry",
                    task_id,
                    task_title,
                    verdict=verdict,
                    feedback=feedback,
                    retry_count=retry_count,
                )
                print(f"HITL: user chose RETRY" + (f" — feedback: {feedback}" if feedback else ""))
                notify(f"\U0001f504 Retrying task {task_id}...")
                if not self.run_reimplement(task_id, task_title, feedback) or self.blocked.reason:
                    _update_task(index, "failed", harness, reason=self.blocked.value)
                    return

                self._set_phase(PhaseName.REVIEW, task_id, task_title)
                self.phase_runner.run(
                    PHASE_REGISTRY[PhaseName.REVIEW],
                    self._task_variables(task_id, task_title),
                    phase_name_override=f"review[{task_id}]",
                    log=self.log,
                )
                if not self._checkpoint() or self.blocked.reason:
                    _update_task(index, "failed", harness, reason=self.blocked.value)
                    return

                new_verdict = _audit_verdict(harness)
                if new_verdict == "APPROVED":
                    print(f"Task {task_id} APPROVED after retry")
                    notify(f"\u2705 Task {task_id} APPROVED after retry")
                    stage_task_files(harness)
                    _update_task(index, "completed", harness)
                    self.compact_fn(task_id=task_id, task_title=task_title)
                    return
                if new_verdict == "MINOR_CHANGES":
                    print(f"Task {task_id} MINOR_CHANGES after retry — fast-path reimplement...")
                    notify(f"\U0001f527 Task {task_id} MINOR_CHANGES — fast-path reimplement")
                    retry_count = self._increment_retry(task_id)
                    self._write_intervention(
                        "auto_reimplement",
                        task_id,
                        task_title,
                        source="system",
                        verdict=new_verdict,
                        retry_count=retry_count,
                    )
                    if not self.run_reimplement(task_id, task_title, "") or self.blocked.reason:
                        _update_task(index, "failed", harness, reason=self.blocked.value)
                        return
                    print(f"Task {task_id} APPROVED after fast-path reimplement")
                    notify(f"\u2705 Task {task_id} APPROVED after fast-path")
                    stage_task_files(harness)
                    _update_task(index, "completed", harness)
                    self.compact_fn(task_id=task_id, task_title=task_title)
                    return
                print("HITL: still CHANGES_REQUESTED after retry, asking user again...")
                continue

            if decision == "skip":
                self._write_intervention("skip", task_id, task_title, verdict=verdict)
                print(f"HITL: user chose SKIP for {task_id}")
                notify(f"\u23ed\ufe0f Task {task_id} skipped by user")
                _update_task(index, "failed", harness)
                return

            if decision == "approve":
                self._write_intervention("force_approve", task_id, task_title, verdict=verdict)
                print(f"Task {task_id} force-approved by user despite {verdict}")
                notify(f"\u2705 Task {task_id} force-approved by user")
                stage_task_files(harness)
                _update_task(index, "completed", harness)
                self.compact_fn(task_id=task_id, task_title=task_title)
                return

    def _next_interaction_command(
        self,
        interaction: Interaction,
        allowed: set[str],
    ) -> CommandEnvelope:
        while True:
            if self.mission_state.control_state == ControlState.ABORT_PENDING:
                return CommandEnvelope("abort", source="state")
            try:
                raw = self.command_queue.get(timeout=5)
            except queue.Empty:
                continue
            cmd = coerce_envelope(raw)
            if cmd.name == "abort":
                return cmd
            if cmd.name == "gate" and cmd.get("mode") in {"manual", "auto"}:
                _apply_gate_change(cmd["mode"], self.ctx.harness, self.mission_state)
                continue
            if cmd.name not in allowed:
                continue
            if not self.mission_state.interaction_accepts(cmd.interaction_id, cmd.update_id):
                continue
            return cmd

    def _checkpoint(self) -> bool:
        return control_checkpoint(
            self.command_queue,
            self.ctx.harness,
            self.mission_state,
            self.blocked,
        )

    def _abort(self) -> None:
        self.blocked.reason = BlockReason(BlockKind.USER_ABORT)
        self.mission_state.set_control_state(ControlState.ABORTED)

    def _set_phase(self, phase: str, task_id: str, task_title: str) -> None:
        snapshot = self.mission_state.snapshot()
        update_state(
            phase,
            self.ctx.harness,
            self.mission_state,
            task_id=task_id,
            task_title=task_title,
            task_num=snapshot["task_num"],
            task_count=snapshot["task_count"],
            completed=snapshot["completed"],
            mode=snapshot["mode"],
            gate=snapshot["gate"],
        )

    def _task_variables(self, task_id: str, task_title: str) -> dict[str, str]:
        task = {"id": task_id, "title": task_title}
        tasks_path = self.ctx.harness / "tasks.json"
        if tasks_path.is_file():
            try:
                tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                tasks = []
            for candidate in tasks:
                if candidate.get("id") == task_id:
                    task = candidate
                    break
        return {
            "TASK_ID": task_id,
            "TASK_TITLE": task_title,
            "TASK_COMPLEXITY": self.ctx.get_task_complexity(task),
            "TASK_PIPELINE": self.ctx.get_task_pipeline_label(task),
            "TASK_COMPLEXITY_REASON": self.ctx.get_task_complexity_reason(task),
        }

    def _increment_retry(self, task_id: str) -> int:
        self._retry_counts[task_id] = self._retry_counts.get(task_id, 0) + 1
        return self._retry_counts[task_id]

    def _write_intervention(
        self,
        action: str,
        task_id: str,
        task_title: str,
        *,
        source: str = "human",
        verdict: str | None = None,
        feedback: str | None = None,
        retry_count: int | None = None,
        missing_component: str | None = None,
    ) -> None:
        write_intervention(
            self.ctx.harness,
            action,
            task_id=task_id,
            task_title=task_title,
            source=source,
            verdict=verdict,
            feedback=feedback,
            retry_count=retry_count,
            missing_component=missing_component,
        )
