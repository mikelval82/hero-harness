from __future__ import annotations

import json
import queue
from typing import TYPE_CHECKING, Callable

from src.core.block_state import BlockKind, BlockReason, BlockState
from src.core.notification import notify
from src.core.state import update_state, _apply_gate_change, MissionStateProtocol
from src.core.context import PHASE_REGISTRY, PhaseName, MissionContext
from src.harness.tasks import (
    update_task as _update_task,
    audit_verdict as _audit_verdict,
    stage_task_files,
)
from src.harness.telemetry import write_intervention

if TYPE_CHECKING:
    from src.mission.phase_runner import PhaseRunner


class HitlReviewer:

    def __init__(
        self,
        ctx: MissionContext,
        phase_runner: PhaseRunner,
        command_queue: queue.Queue[dict],
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
            if gate == "manual":
                ok = self.wait_approval(task_id, task_title)
                if not ok:
                    return
            print(f"Task {task_id} APPROVED")
            notify(f"✅ Task {task_id} APPROVED")
            stage_task_files(harness)
            _update_task(index, "completed", harness)
            self.compact_fn(task_id=task_id, task_title=task_title)
        elif verdict == "MINOR_CHANGES":
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
            notify(f"✅ Task {task_id} APPROVED after fast-path")
            stage_task_files(harness)
            _update_task(index, "completed", harness)
            self.compact_fn(task_id=task_id, task_title=task_title)
        else:
            self.hitl_review_loop(index, task_id, task_title)

    def run_reimplement(self, task_id: str, task_title: str, user_feedback: str) -> None:
        if user_feedback:
            feedback_block = f"Additional feedback from the user: {user_feedback}"
        else:
            feedback_block = "No additional user feedback. Focus on the reviewer's audit."
        self.phase_runner.run(
            PHASE_REGISTRY[PhaseName.REIMPLEMENT],
            {**self._task_variables(task_id, task_title), "USER_FEEDBACK": feedback_block},
            phase_name_override=f"reimplement[{task_id}]", log=self.log)

    def wait_approval(self, task_id: str, task_title: str) -> bool:
        harness = self.ctx.harness
        verdict = _audit_verdict(harness)
        self._write_intervention(
            "waiting_approval",
            task_id,
            task_title,
            source="system",
            verdict=verdict,
        )
        self.mission_state.waiting_approval = {
            "task_id": task_id,
            "task_title": task_title,
            "verdict": verdict,
        }
        self.mission_state.waiting_notified = False
        notify(f"⏳ Waiting for approval: {task_id} — {task_title} (reviewer: {verdict}). Reply /approve or /reject")
        update_state("waiting_approval", harness, self.mission_state)

        while True:
            try:
                cmd = self.command_queue.get(timeout=5)
            except queue.Empty:
                continue
            action = cmd.get("cmd", "")
            if action == "approve":
                self._write_intervention("approve", task_id, task_title, verdict=verdict)
                self.mission_state.waiting_approval = None
                self.mission_state.waiting_notified = False
                return True
            elif action == "reject":
                reason = cmd.get("reason", "")
                self._write_intervention("reject", task_id, task_title, verdict=verdict, feedback=reason)
                self.mission_state.waiting_approval = None
                self.mission_state.waiting_notified = False
                self.blocked.reason = BlockReason(BlockKind.USER_REJECTED, phase=task_id, detail=reason)
                notify(f"❌ Task {task_id} REJECTED by user{' — ' + reason if reason else ''}")
                return False
            elif action == "abort":
                self._write_intervention("abort", task_id, task_title, verdict=verdict)
                self.mission_state.waiting_approval = None
                self.mission_state.waiting_notified = False
                self.blocked.reason = BlockReason(BlockKind.USER_ABORT)
                return False
            elif action == "pause":
                self._write_intervention("pause", task_id, task_title, verdict=verdict)
                if not self._wait_pause_resume():
                    self.mission_state.waiting_approval = None
                    self.mission_state.waiting_notified = False
                    self.blocked.reason = BlockReason(BlockKind.USER_ABORT)
                    return False
            elif action == "gate":
                self._write_intervention("gate_change", task_id, task_title, verdict=verdict, feedback=cmd["mode"])
                _apply_gate_change(cmd["mode"], harness, self.mission_state)

    def _wait_pause_resume(self) -> bool:
        while True:
            try:
                cmd = self.command_queue.get(timeout=5)
            except queue.Empty:
                continue
            action = cmd.get("cmd", "")
            if action == "resume":
                return True
            if action == "abort":
                return False
            if action == "gate":
                _apply_gate_change(cmd["mode"], self.ctx.harness, self.mission_state)

    def hitl_review_loop(self, index: int, task_id: str, task_title: str) -> None:
        harness = self.ctx.harness
        while True:
            verdict = _audit_verdict(harness)
            self._write_intervention(
                "waiting_review_decision",
                task_id,
                task_title,
                source="system",
                verdict=verdict,
            )
            self.mission_state.waiting_approval = {
                "task_id": task_id,
                "task_title": task_title,
                "verdict": verdict,
            }
            self.mission_state.waiting_notified = False
            update_state("waiting_review_decision", harness, self.mission_state)
            print(f"HITL: waiting for user decision on {task_id} (reviewer: {verdict})...")

            decision = None
            cmd_data = None
            while decision is None:
                try:
                    cmd = self.command_queue.get(timeout=5)
                except queue.Empty:
                    continue
                action = cmd.get("cmd", "")
                if action in ("retry", "skip", "approve", "abort"):
                    decision = action
                    cmd_data = cmd
                elif action == "pause":
                    if not self._wait_pause_resume():
                        decision = "abort"
                        break
                elif action == "gate":
                    _apply_gate_change(cmd["mode"], harness, self.mission_state)

            self.mission_state.waiting_approval = None
            self.mission_state.waiting_notified = False

            if decision == "retry":
                feedback = cmd_data.get("feedback", "")
                retry_count = self._increment_retry(task_id)
                self._write_intervention(
                    "retry",
                    task_id,
                    task_title,
                    verdict=verdict,
                    feedback=feedback,
                    retry_count=retry_count,
                )
                print(f"HITL: user chose RETRY{' — feedback: ' + feedback if feedback else ''}")
                notify(f"\U0001f504 Retrying task {task_id}...")
                self.run_reimplement(task_id, task_title, feedback)
                if self.blocked.reason:
                    _update_task(index, "failed", harness, reason=self.blocked.value)
                    return
                self.phase_runner.run(
                    PHASE_REGISTRY[PhaseName.REVIEW],
                    self._task_variables(task_id, task_title),
                    phase_name_override=f"review[{task_id}]", log=self.log)
                if self.blocked.reason:
                    _update_task(index, "failed", harness, reason=self.blocked.value)
                    return
                new_verdict = _audit_verdict(harness)
                if new_verdict == "APPROVED":
                    print(f"Task {task_id} APPROVED after retry")
                    notify(f"✅ Task {task_id} APPROVED after retry")
                    stage_task_files(harness)
                    _update_task(index, "completed", harness)
                    self.compact_fn(task_id=task_id, task_title=task_title)
                    return
                elif new_verdict == "MINOR_CHANGES":
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
                    self.run_reimplement(task_id, task_title, "")
                    if self.blocked.reason:
                        _update_task(index, "failed", harness, reason=self.blocked.value)
                        return
                    print(f"Task {task_id} APPROVED after fast-path reimplement")
                    notify(f"✅ Task {task_id} APPROVED after fast-path")
                    stage_task_files(harness)
                    _update_task(index, "completed", harness)
                    self.compact_fn(task_id=task_id, task_title=task_title)
                    return
                print("HITL: still CHANGES_REQUESTED after retry, asking user again...")

            elif decision == "skip":
                self._write_intervention("skip", task_id, task_title, verdict=verdict)
                print(f"HITL: user chose SKIP for {task_id}")
                notify(f"⏭️ Task {task_id} skipped by user")
                _update_task(index, "failed", harness)
                return

            elif decision == "approve":
                self._write_intervention("force_approve", task_id, task_title, verdict=verdict)
                print(f"Task {task_id} force-approved by user despite {verdict}")
                notify(f"✅ Task {task_id} force-approved by user")
                stage_task_files(harness)
                _update_task(index, "completed", harness)
                self.compact_fn(task_id=task_id, task_title=task_title)
                return

            elif decision == "abort":
                self._write_intervention("abort", task_id, task_title, verdict=verdict)
                self.blocked.reason = BlockReason(BlockKind.USER_ABORT)
                _update_task(index, "failed", harness, reason="user_abort")
                return

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
