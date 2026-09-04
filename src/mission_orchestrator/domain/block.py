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

    @property
    def recoverable(self) -> bool:
        return self not in {
            BlockKind.USER_ABORT,
            BlockKind.USER_REJECTED,
            BlockKind.SIGNAL,
        }


@dataclass(frozen=True)
class BlockReason:
    kind: BlockKind
    phase: str = ""
    detail: str = ""

    @property
    def is_mission_abort(self) -> bool:
        return self.kind in {BlockKind.USER_ABORT, BlockKind.SIGNAL}

    @property
    def recoverable(self) -> bool:
        return self.kind.recoverable

    @property
    def recovery_action(self) -> str:
        if not self.recoverable:
            return "abort"
        if self.kind is BlockKind.GATE_FAIL and "changeset has unresolved issues" in self.detail:
            return "retry-design"
        if self.phase == "review":
            return "retry-review"
        if self.phase in {"spec", "plan", "implement", "implement_bursts", "reimplement"}:
            return "retry-preparation" if self.phase in {"spec", "plan"} else "resume"
        return "resume"

    def to_json(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "phase": self.phase,
            "detail": self.detail,
            "recoverable": self.recoverable,
            "recovery_action": self.recovery_action,
        }

    def __str__(self) -> str:
        bits = [self.kind.value]
        if self.phase:
            bits.append(f"phase={self.phase}")
        if self.detail:
            bits.append(self.detail)
        return " | ".join(bits)
