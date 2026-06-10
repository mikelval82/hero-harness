from __future__ import annotations

import json
from queue import Queue
from typing import Any, Callable

from src.mission.phase_runner import PhaseRunner
from src.core.block_state import BlockKind, BlockReason, BlockState
from src.core.notification import notify
from src.core.state import update_state, MissionStateProtocol
from src.mission.signals import check_signals
from src.mission.human_input import HumanInput
from src.mission.reporting import (
    generate_report, _consolidate_tasks, notify_result, build_code_graph,
)
from src.core.context import PHASE_REGISTRY, PhaseName, MissionContext
from src.core.git import merge_to_develop, final_commit
from src.mission.burst_runner import BurstRunner
from src.mission.hitl import HitlReviewer
from src.mission.task_executor import TaskExecutor
from src.harness.project_memory import sync_project_memory
from src.harness.case_base import save_approved_mission_case
from src.harness.skill_library import sync_generated_skills
from src.harness.tasks import (
    update_task as _update_task,
    task_summary as _task_summary,
    stage_task_files,
)


class MissionRunner:

    def __init__(
        self,
        client: Any,
        ctx: MissionContext,
        command_queue: Queue[dict],
        mission_state: MissionStateProtocol,
        log: Callable[[str], None],
        blocked: BlockState,
        phase_runner: PhaseRunner,
        burst: BurstRunner,
        hitl: HitlReviewer,
        task_executor: TaskExecutor,
    ) -> None:
        self.client = client
        self.ctx = ctx
        self.command_queue = command_queue
        self.mission_state = mission_state
        self.log = log
        self.blocked = blocked
        self.phase_runner = phase_runner
        self.burst = burst
        self.hitl = hitl
        self.task_executor = task_executor

    def execute(self) -> None:
        harness = self.ctx.harness
        tasks_path = harness / "tasks.json"
        resuming = self.ctx.resume and tasks_path.is_file()

        if resuming:
            self.log("Mission RESUMED (skipping research/structure/grill)")
            notify(f"Mission resumed: {self.ctx.task}\nBranch: {self.ctx.branch} | Mode: {self.ctx.mode}")
        else:
            self.log("Mission started")
            notify(f"Mission started: {self.ctx.task}\nBranch: {self.ctx.branch} | Mode: {self.ctx.mode}")

            if not self._run_init_phases():
                return

        if self.ctx.mode == "explore":
            self.log("Explore mode — skipping task loop")
            self._run_finalize(0)
            return

        if not tasks_path.is_file():
            self.log("ERROR: research/structure did not produce tasks.json")
            print("ERROR: research/structure did not produce tasks.json")
            notify_result(self.ctx.task, self.ctx.branch, harness, self.blocked)
            return

        tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
        task_count = len(tasks)
        completed = 0
        self.log(f"Loaded {task_count} tasks")

        if not resuming and task_count > self.ctx.max_tasks:
            self.log(f"Task count ({task_count}) exceeds limit ({self.ctx.max_tasks}), consolidating...")
            _consolidate_tasks(self.client, harness=harness, harness_win=self.ctx.harness_win,
                               project_dir=self.ctx.project_dir, max_tasks=self.ctx.max_tasks, log=self.log)
            tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
            task_count = len(tasks)
            self.log(f"After consolidation: {task_count} tasks")

        completed = self._run_task_loop(tasks, task_count)
        self._run_finalize(completed)

    def _run_init_phases(self) -> bool:
        harness = self.ctx.harness
        ctx = self.ctx
        pipeline = ctx.get_mission_pipeline()

        build_code_graph(ctx.project_dir, log=self.log)

        for step in pipeline["init"]:
            optional = step.endswith("?")
            phase_name = step.rstrip("?")

            if phase_name == PhaseName.COMPACT:
                self.burst.compact_context()
                build_code_graph(ctx.project_dir, log=self.log)
                continue

            if phase_name == PhaseName.GRILL:
                if optional and ctx.no_grill:
                    continue
                update_state(PhaseName.GRILL, harness, self.mission_state, mode=ctx.mode)
                get_input = HumanInput(self.command_queue, self.blocked, log=self.log)
                self.phase_runner.run_conversation(
                    PHASE_REGISTRY[PhaseName.GRILL], {"TASK": ctx.task}, get_input, log=self.log)
            elif phase_name == PhaseName.STRUCTURE:
                update_state(PhaseName.STRUCTURE, harness, self.mission_state, mode=ctx.mode)
                self.phase_runner.run(PHASE_REGISTRY[PhaseName.STRUCTURE], {"TASK": ctx.task}, log=self.log)
                if not self.blocked.reason:
                    tasks_file = harness / "tasks.json"
                    try:
                        tasks_data = json.loads(tasks_file.read_text(encoding="utf-8"))
                        if not isinstance(tasks_data, list) or len(tasks_data) == 0:
                            self.blocked.reason = BlockReason(BlockKind.STRUCTURE, detail="tasks.json is empty or not a list")
                    except (FileNotFoundError, json.JSONDecodeError) as exc:
                        self.blocked.reason = BlockReason(BlockKind.STRUCTURE, detail=f"invalid tasks.json — {exc}")
            else:
                update_state(phase_name, harness, self.mission_state, mode=ctx.mode)
                self.phase_runner.run(PHASE_REGISTRY[PhaseName(phase_name)], {"TASK": ctx.task}, log=self.log)

            if self.blocked.reason:
                self.log(f"<<< Mission BLOCKED: {self.blocked.value}")
                self._generate_report()
                notify_result(ctx.task, ctx.branch, harness, self.blocked)
                return False

            if not check_signals(self.command_queue, harness, self.mission_state, self.blocked):
                self.log(f"<<< Mission BLOCKED: {self.blocked.value}")
                self._generate_report()
                notify_result(ctx.task, ctx.branch, harness, self.blocked)
                return False

        return True

    def _run_task_loop(self, tasks: list[dict], task_count: int) -> int:
        self.task_executor.log = self.log
        return self.task_executor.run(tasks, task_count)

    def _run_finalize(self, completed: int) -> None:
        ctx = self.ctx
        pipeline = ctx.get_mission_pipeline()
        finalize_steps = pipeline["finalize"]
        has_merge = "merge" in finalize_steps

        if has_merge:
            final_commit(ctx.task, _task_summary(ctx.harness))

        self._generate_report()
        notify_result(ctx.task, ctx.branch, ctx.harness, self.blocked)

        if self.blocked.reason:
            self.log(f"Mission BLOCKED: {self.blocked.value}")
        else:
            final_tasks_path = ctx.harness / "tasks.json"
            final_tasks = json.loads(final_tasks_path.read_text(encoding="utf-8")) if final_tasks_path.is_file() else []
            failed_count = sum(1 for t in final_tasks if t.get("status") == "failed")
            if failed_count > 0:
                self.log(f"Mission partial: {_task_summary(ctx.harness)}")
            else:
                self.log("Mission complete")
            if has_merge:
                merged = merge_to_develop(ctx.branch, self.log)
                if merged:
                    notify(f"Merged {ctx.branch} → develop")
                else:
                    notify(f"Branch {ctx.branch} NOT merged (tests failed or conflict)")

    def _generate_report(self) -> None:
        generate_report(self.client, task=self.ctx.task, branch=self.ctx.branch,
                        mode=self.ctx.mode, harness=self.ctx.harness,
                        harness_win=self.ctx.harness_win,
                        project_dir=self.ctx.project_dir, blocked=self.blocked,
                        log=self.log)
        synced_skills = sync_generated_skills(self.ctx.harness)
        if synced_skills:
            self.log(f"Verified skills synced: {synced_skills}")
        if save_approved_mission_case(
            self.ctx.harness,
            task=self.ctx.task,
            branch=self.ctx.branch,
            mode=self.ctx.mode,
            project_dir=self.ctx.project_dir,
            blocked=self.blocked,
        ):
            self.log("Mission case saved")
        if sync_project_memory(self.ctx.harness):
            self.log("Project memory synced")


def create_runner(
    client: Any,
    ctx: MissionContext,
    command_queue: Queue[dict],
    mission_state: MissionStateProtocol,
    log: Callable[[str], None],
    blocked: BlockState,
) -> MissionRunner:
    phase_runner = PhaseRunner(client, ctx, blocked)
    burst = BurstRunner(client, ctx, phase_runner, blocked, log)
    hitl = HitlReviewer(ctx, phase_runner, command_queue, mission_state,
                        blocked, log, burst.compact_context)
    task_executor = TaskExecutor(
        ctx, phase_runner, burst, hitl,
        command_queue, mission_state, blocked, log,
        check_signals_fn=check_signals,
        update_state_fn=update_state,
        build_code_graph_fn=build_code_graph,
        notify_fn=notify,
        stage_task_files_fn=stage_task_files,
        update_task_fn=_update_task,
    )
    return MissionRunner(client, ctx, command_queue, mission_state, log, blocked,
                         phase_runner, burst, hitl, task_executor)
