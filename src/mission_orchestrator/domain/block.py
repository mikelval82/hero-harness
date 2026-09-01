from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BlockKind(Enum):
    USER_ABORT = "user_abort"
    SIGNAL = "signal"
    TIMEOUT = "timeout"
    MAX_TURNS = "max_turns"
    API_RETRIES = "api_retries"
    USAGE_LIMIT = "usage_limit"
    TOKEN_BUDGET = "token_budget"
    GATE_FAIL = "gate_fail"
    POLICY = "policy"
    USER_REJECTED = "user_rejected"
    STRUCTURE = "structure"


@dataclass(frozen=True)
class BlockReason:
    kind: BlockKind
    phase: str = ""
    detail: str = ""

    @property
    def is_mission_abort(self) -> bool:
        return self.kind in {BlockKind.USER_ABORT, BlockKind.SIGNAL}

    def __str__(self) -> str:
        bits = [self.kind.value]
        if self.phase:
            bits.append(f"phase={self.phase}")
        if self.detail:
            bits.append(self.detail)
        return " | ".join(bits)
