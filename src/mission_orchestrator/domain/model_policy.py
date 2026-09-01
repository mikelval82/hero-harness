from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSelection:
    requested_provider: str
    requested_model: str
    tier: str
    reason: str
    policy_version: str
