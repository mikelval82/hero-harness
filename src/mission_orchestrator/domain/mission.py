from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class MissionMode(Enum):
    FULL = "full"
    FOCUSED = "focused"
    PLAN = "plan"
    EXPLORE = "explore"
    HOTFIX = "hotfix"


class GateMode(Enum):
    AUTO = "auto"
    MANUAL = "manual"

    @classmethod
    def from_bool(cls, enabled: bool) -> "GateMode":
        return cls.MANUAL if enabled else cls.AUTO


@dataclass(frozen=True)
class MissionContext:
    task: str
    branch: str
    mode: MissionMode
    project_dir: Path
    harness_dir: Path
    harness_display_path: str
    gate_mode: GateMode
    no_grill: bool
    max_tasks: int
    resume: bool
    mission_tag: str
    project_name: str
    project_scope_dir: Path | None = None


@dataclass(frozen=True)
class MissionSnapshot:
    phase: str
    task_id: str = ""
    task_title: str = ""
    task_num: int = 0
    task_count: int = 0
    completed: int = 0
    mode: str = ""
    gate: str = "auto"

    def to_json(self) -> dict[str, object]:
        return {
            "phase": self.phase,
            "task_id": self.task_id,
            "task_title": self.task_title,
            "task_num": self.task_num,
            "task_count": self.task_count,
            "completed": self.completed,
            "mode": self.mode,
            "gate": self.gate,
        }

    @classmethod
    def from_json(cls, data: dict[str, object]) -> "MissionSnapshot":
        return cls(
            phase=str(data.get("phase", "")),
            task_id=str(data.get("task_id", "")),
            task_title=str(data.get("task_title", "")),
            task_num=int(data.get("task_num", 0) or 0),
            task_count=int(data.get("task_count", 0) or 0),
            completed=int(data.get("completed", 0) or 0),
            mode=str(data.get("mode", "")),
            gate=str(data.get("gate", "auto")),
        )


@dataclass(frozen=True)
class WaitingApproval:
    task_id: str
    task_title: str
    verdict: str
    notified: bool = False

    def to_json(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "task_title": self.task_title,
            "verdict": self.verdict,
            "notified": self.notified,
        }

    @classmethod
    def from_json(cls, data: dict[str, object]) -> "WaitingApproval":
        return cls(
            task_id=str(data.get("task_id", "")),
            task_title=str(data.get("task_title", "")),
            verdict=str(data.get("verdict", "")),
            notified=bool(data.get("notified", False)),
        )

