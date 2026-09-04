from __future__ import annotations

from mission_orchestrator.domain.mission import MissionMode
from mission_orchestrator.domain.phase import PhaseName
from mission_orchestrator.domain.pipeline import MissionPipeline, TaskPipeline
from mission_orchestrator.domain.task import Task, TaskComplexity


def mission_pipeline_for(mode: MissionMode, *, no_grill: bool) -> MissionPipeline:
    grill = () if no_grill else (PhaseName.GRILL,)
    if mode == MissionMode.FULL:
        return MissionPipeline(
            init=(PhaseName.RESEARCH, PhaseName.COMPACT, *grill, PhaseName.STRUCTURE),
            task_loop=True,
            finalize=(PhaseName.REPORT,),
        )
    if mode == MissionMode.SIMPLE:
        return MissionPipeline(
            init=(PhaseName.RESEARCH, PhaseName.STRUCTURE),
            task_loop=True,
            finalize=(PhaseName.REPORT,),
        )
    if mode == MissionMode.FOCUSED:
        return MissionPipeline(
            init=(PhaseName.RESEARCH, PhaseName.STRUCTURE),
            task_loop=True,
            finalize=(PhaseName.REPORT,),
        )
    if mode == MissionMode.PLAN:
        return MissionPipeline(
            init=(PhaseName.RESEARCH, *grill, PhaseName.STRUCTURE),
            task_loop=True,
            finalize=(PhaseName.REPORT_PLAN,),
        )
    if mode == MissionMode.SPEC:
        return MissionPipeline(init=(), task_loop=False, finalize=(PhaseName.SPEC, PhaseName.REPORT_PLAN))
    if mode == MissionMode.EXPLORE:
        return MissionPipeline(
            init=(PhaseName.RESEARCH,),
            task_loop=False,
            finalize=(PhaseName.REPORT_PLAN,),
        )
    if mode == MissionMode.HOTFIX:
        return MissionPipeline(init=(), task_loop=True, finalize=(PhaseName.REPORT,))
    raise ValueError(f"Unsupported mode: {mode}")


def task_pipeline_for(task: Task, mode: MissionMode) -> TaskPipeline:
    if mode == MissionMode.PLAN:
        return TaskPipeline((PhaseName.SPEC, PhaseName.PLAN))
    if task.complexity == TaskComplexity.S:
        return TaskPipeline((PhaseName.SPEC, PhaseName.PLAN, PhaseName.IMPLEMENT))
    if task.complexity == TaskComplexity.M:
        return TaskPipeline((PhaseName.SPEC, PhaseName.PLAN, PhaseName.IMPLEMENT, PhaseName.REVIEW))
    if task.complexity == TaskComplexity.L:
        return TaskPipeline(
            (PhaseName.SPEC, PhaseName.PLAN, PhaseName.IMPLEMENT_BURSTS, PhaseName.REVIEW)
        )
    return TaskPipeline((PhaseName.SPEC, PhaseName.PLAN, PhaseName.IMPLEMENT, PhaseName.REVIEW))


def mode_should_merge(mode: MissionMode) -> bool:
    return mode in {MissionMode.FULL, MissionMode.SIMPLE, MissionMode.FOCUSED, MissionMode.HOTFIX}
