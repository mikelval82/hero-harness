from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from mission_orchestrator.domain.block import BlockReason


class MissionOutcome(Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class MissionResult:
    outcome: MissionOutcome
    summary: str
    completed: int = 0
    failed: int = 0
    block: BlockReason | None = None
    report_preview: str = ""

