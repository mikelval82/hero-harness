from __future__ import annotations

from enum import Enum


class ProviderOutcome(str, Enum):
    COMPLETED = "completed"
    TOOL_USE = "tool_use"
    TRUNCATED = "truncated"
    REFUSED = "refused"
    PAUSED = "paused"
    MALFORMED = "malformed"


class ProviderOutcomeError(RuntimeError):
    pass
