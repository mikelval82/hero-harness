from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from queue import Queue
from typing import TYPE_CHECKING, Any, Callable

from src.core.block_state import BlockState
from src.core.context import PHASE_REGISTRY, PhaseName, MissionContext
from src.core.state import MissionStateProtocol
from src.harness.telemetry import write_task_event

if TYPE_CHECKING:
    from src.mission.phase_runner import PhaseRunner
    from src.mission.burst_runner import BurstRunner
    from src.mission.hitl import HitlReviewer


STALE_TASK_ARTIFACTS = (
    "spec.md",
    "plan.md",
    "decisions.md",
    "status.md",
    "audit.md",
    "_burst_progress.md",
)


@dataclass(frozen=True)
class TaskResult:
    completed: bool = False
    aborted: bool = False
    failed: bool = False


class TaskExecutor:

    def __init__(
        self,
        ctx: MissionContext,
        phase_runner: PhaseRunner,
        burst_runner: BurstRunner,
        hitl_reviewer: HitlReviewer,
        command_queue: Queue[dict],
        mission_state: MissionStateProtocol,
        blocked: BlockState,
        log: Callable[[str], None],
        *,
        check_signals_fn: Callable[..., bool],
        update_state_fn: Callable[..., None],
        build_code_graph_fn: Callable[..., None],
        notify_fn: Callable[[str], None],
        stage_task_files_fn: Callable[..., None],
        update_task_fn: Callable[..., None],
    ) -> None:
        self.ctx = ctx
        self.phase_runner = phase_runner
        self.burst = burst_runner
        self.hitl = hitl_reviewer
        self.command_queue = command_queue
        self.mission_state = mission_state
        self.blocked = blocked
        self.log = log
        self.check_signals = check_signals_fn
        self.update_state = update_state_fn
        self.build_code_graph = build_code_graph_fn
        self.notify = notify_fn
        self.stage_task_files = stage_task_files_fn
        self.update_task = update_task_fn
        self._last_task_failure_reason = ""

    def run(self, tasks: list[dict], task_count: int) -> int:
        completed = 0
        for index, task in enumerate(tasks):
            if self.blocked.is_mission_abort:
                break
            if not self.check_signals(
                self.command_queue,
                self.ctx.harness,
                self.mission_state,
                self.blocked,
            ):
                break

            result = self.run_task(index, task, task_count, completed)
            if result.completed:
                completed += 1
            if result.aborted:
                break
        return completed

    def run_task(self, index: int, task: dict, task_count: int, completed: int) -> TaskResult:
        task_id = task["id"]
        task_title = task["title"]
        self._last_task_failure_reason = ""
        if task.get("status") == "completed":
            return TaskResult(completed=True)

        self._clear_task_artifacts()
        self.build_code_graph(self.ctx.project_dir, log=self.log)

        pipeline = self._task_pipeline(task)
        complexity = self.ctx.get_task_complexity(task)
        complexity_reason = self.ctx.get_task_complexity_reason(task)
        pipeline_label = " -> ".join(phase.value for phase in pipeline)
        self.log(
            f"=== Task {index + 1}/{task_count}: [{task_id}] {task_title} "
            f"(complexity={complexity}, complexity_reason={complexity_reason}, "
            f"pipeline={pipeline_label})"
        )
        print(f"\n{'='*60}")
        print(f"Task {index + 1}/{task_count}: [{task_id}] {task_title}")
        print(f"Routing: {complexity} ({pipeline_label})")
        print(f"Routing reason: {complexity_reason}")
        print(f"{'='*60}")
        self._write_task_event(
            "task_started",
            task_id=task_id,
            task_title=task_title,
            status="started",
            complexity=complexity,
            pipeline=pipeline_label,
            complexity_reason=complexity_reason,
        )

        task_vars = self._task_variables(task_id, task_title, task)
        if not self._run_task_phases(index, task_id, task_vars, pipeline, task_count, completed):
            status = "aborted" if self._is_abort() else "failed"
            self._write_task_event(
                "task_failed",
                task_id=task_id,
                task_title=task_title,
                status=status,
                complexity=complexity,
                pipeline=pipeline_label,
                complexity_reason=complexity_reason,
                failure_reason=self.blocked.value or self._last_task_failure_reason,
                missing_component="phase_recovery",
            )
            return TaskResult(aborted=self._is_abort(), failed=not self._is_abort())

        if self._is_abort():
            self._write_task_event(
                "task_failed",
                task_id=task_id,
                task_title=task_title,
                status="aborted",
                complexity=complexity,
                pipeline=pipeline_label,
                complexity_reason=complexity_reason,
                failure_reason="mission_abort",
                missing_component="user_input",
            )
            return TaskResult(aborted=True)

        if self.ctx.is_partial_harness_mode():
            self.update_task(index, "completed", self.ctx.harness)
            self.log(f"Task {task_id} completed ({self.ctx.mode} partial harness)")
            self._write_task_event(
                "task_completed",
                task_id=task_id,
                task_title=task_title,
                status="completed",
                complexity=complexity,
                pipeline=pipeline_label,
                complexity_reason=complexity_reason,
            )
            self.burst.compact_context(task_id=task_id, task_title=task_title)
            if self.blocked.reason and not self._is_abort():
                self.blocked.reason = None
            return TaskResult(completed=True)

        self._complete_or_review(index, task_id, task_title, pipeline)
        if self.blocked.reason:
            if self._is_abort():
                self._write_task_event(
                    "task_failed",
                    task_id=task_id,
                    task_title=task_title,
                    status="aborted",
                    complexity=complexity,
                    pipeline=pipeline_label,
                    complexity_reason=complexity_reason,
                    failure_reason=self.blocked.value,
                    missing_component="user_input",
                )
                return TaskResult(aborted=True)
            self.log(f"Task {task_id} FAILED: {self.blocked.value}")
            self._write_task_event(
                "task_failed",
                task_id=task_id,
                task_title=task_title,
                status="failed",
                complexity=complexity,
                pipeline=pipeline_label,
                complexity_reason=complexity_reason,
                failure_reason=self.blocked.value,
                missing_component="review_recovery",
            )
            self.blocked.reason = None
            return TaskResult(failed=True)

        if self._task_completed(index):
            self._write_task_event(
                "task_completed",
                task_id=task_id,
                task_title=task_title,
                status="completed",
                complexity=complexity,
                pipeline=pipeline_label,
                complexity_reason=complexity_reason,
            )
            return TaskResult(completed=True)
        if self._task_failed(index):
            self._write_task_event(
                "task_failed",
                task_id=task_id,
                task_title=task_title,
                status="failed",
                complexity=complexity,
                pipeline=pipeline_label,
                complexity_reason=complexity_reason,
                failure_reason="task status failed",
                missing_component="hitl_recovery",
            )
            return TaskResult(failed=True)
        return TaskResult()

    def _run_task_phases(
        self,
        index: int,
        task_id: str,
        task_vars: dict,
        pipeline: list[PhaseName],
        task_count: int,
        completed: int,
    ) -> bool:
        task_title = task_vars["TASK_TITLE"]
        for phase_name in pipeline:
            if self._is_abort():
                return False

            state_name = PhaseName.IMPLEMENT if phase_name == PhaseName.IMPLEMENT_BURSTS else phase_name
            self.update_state(
                state_name,
                self.ctx.harness,
                self.mission_state,
                task_id=task_id,
                task_title=task_title,
                task_num=index + 1,
                task_count=task_count,
                completed=completed,
                mode=self.ctx.mode,
            )

            self._run_phase(phase_name, task_id, task_vars)
            if phase_name == PhaseName.PLAN:
                self._ensure_decisions_file()

            if self.blocked.reason:
                if self._is_abort():
                    return False
                self.log(f"Task {task_id} FAILED at {phase_name}: {self.blocked.value}")
                self.update_task(index, "failed", self.ctx.harness, reason=self.blocked.value)
                self._last_task_failure_reason = self.blocked.value
                self.blocked.reason = None
                return False
        return True

    def _run_phase(self, phase_name: PhaseName, task_id: str, task_vars: dict) -> None:
        if phase_name == PhaseName.IMPLEMENT_BURSTS:
            self.burst.run_implement_bursts(task_id, task_vars["TASK_TITLE"], task_vars)
        elif phase_name == PhaseName.IMPLEMENT:
            self.phase_runner.run(
                PHASE_REGISTRY[PhaseName.IMPLEMENT],
                task_vars,
                phase_name_override=f"implement[{task_id}]",
                log=self.log,
            )
        else:
            self.phase_runner.run(
                PHASE_REGISTRY[PhaseName(phase_name)],
                task_vars,
                phase_name_override=f"{phase_name}[{task_id}]",
                log=self.log,
            )

    def _complete_or_review(
        self,
        index: int,
        task_id: str,
        task_title: str,
        pipeline: list[PhaseName],
    ) -> None:
        if PhaseName.REVIEW in pipeline:
            self.hitl.commit_task(index, task_id, task_title)
            return

        print(f"Task {task_id} APPROVED (no review)")
        self.notify(f"✅ Task {task_id} APPROVED (no review)")
        self.stage_task_files(self.ctx.harness)
        self.update_task(index, "completed", self.ctx.harness)
        self.burst.compact_context(task_id=task_id, task_title=task_title)

    def _task_pipeline(self, task: dict) -> list[PhaseName]:
        partial_pipeline = self.ctx.get_partial_task_pipeline()
        if partial_pipeline is not None:
            return partial_pipeline
        return self.ctx.get_task_pipeline(task)

    def _task_variables(self, task_id: str, task_title: str, task: dict) -> dict[str, str]:
        pipeline_label = " -> ".join(phase.value for phase in self._task_pipeline(task))
        return {
            "TASK_ID": task_id,
            "TASK_TITLE": task_title,
            "TASK_COMPLEXITY": self.ctx.get_task_complexity(task),
            "TASK_COMPLEXITY_REASON": self.ctx.get_task_complexity_reason(task),
            "TASK_PIPELINE": pipeline_label,
        }

    def _clear_task_artifacts(self) -> None:
        for stale in STALE_TASK_ARTIFACTS:
            path = self.ctx.harness / stale
            if path.exists():
                path.unlink()

    def _ensure_decisions_file(self) -> None:
        decisions = self.ctx.harness / "decisions.md"
        if not decisions.is_file():
            decisions.write_text(
                "No architectural decisions recorded for this task.\n",
                encoding="utf-8",
            )

    def _task_completed(self, index: int) -> bool:
        tasks_path = self.ctx.harness / "tasks.json"
        updated_tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
        return updated_tasks[index].get("status") == "completed"

    def _task_failed(self, index: int) -> bool:
        tasks_path = self.ctx.harness / "tasks.json"
        updated_tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
        return updated_tasks[index].get("status") == "failed"

    def _is_abort(self) -> bool:
        return self.blocked.is_mission_abort

    def _write_task_event(self, event_type: str, **fields: str) -> None:
        write_task_event(self.ctx.harness, event_type, **fields)
