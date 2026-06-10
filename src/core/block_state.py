from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BlockKind(Enum):
    USER_ABORT = "user_abort"
    SIGNAL = "signal"
    TIMEOUT = "timeout"
    MAX_TURNS = "max_turns"
    API_RETRIES = "api_retries"
    GATE_FAIL = "gate_fail"
    USER_REJECTED = "user_rejected"
    STRUCTURE = "structure"


@dataclass(frozen=True)
class BlockReason:
    kind: BlockKind
    phase: str = ""
    detail: str = ""

    def __str__(self) -> str:
        k = self.kind
        if k == BlockKind.USER_ABORT:
            return "user_abort"
        if k == BlockKind.SIGNAL:
            return f"signal_{self.detail}"
        if k == BlockKind.USER_REJECTED:
            if self.detail:
                return f"review[{self.phase}] (USER_REJECTED: {self.detail})"
            return f"review[{self.phase}] (USER_REJECTED)"
        if k == BlockKind.GATE_FAIL:
            return f"{self.phase} (gate_fail: {self.detail})"
        if k == BlockKind.STRUCTURE:
            return f"structure: {self.detail}"
        return f"{self.phase} ({k.value})"

    @property
    def is_mission_abort(self) -> bool:
        return self.kind in (BlockKind.USER_ABORT, BlockKind.SIGNAL)


class BlockState:
    __slots__ = ("reason",)

    def __init__(self) -> None:
        self.reason: BlockReason | None = None

    @property
    def value(self) -> str:
        return str(self.reason) if self.reason is not None else ""

    @property
    def is_mission_abort(self) -> bool:
        return self.reason is not None and self.reason.is_mission_abort
