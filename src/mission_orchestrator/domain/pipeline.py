from __future__ import annotations

from dataclasses import dataclass

from mission_orchestrator.domain.phase import PhaseName


@dataclass(frozen=True)
class MissionPipeline:
    init: tuple[PhaseName, ...]
    task_loop: bool
    finalize: tuple[PhaseName, ...]


@dataclass(frozen=True)
class TaskPipeline:
    phases: tuple[PhaseName, ...]

