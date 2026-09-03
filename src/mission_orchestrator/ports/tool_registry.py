from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

from mission_orchestrator.domain.phase import PhaseAuthority


@dataclass(frozen=True)
class ToolEnvironment:
    project_dir: Path
    harness_dir: Path


class ToolAccess(Enum):
    READ_ONLY = "read_only"
    PATH_WRITE = "path_write"
    PROJECT_EXECUTION = "project_execution"
    TRUSTED_VALIDATION = "trusted_validation"
    HARNESS_MUTATION = "harness_mutation"


class ToolAuthorizationError(PermissionError):
    def __init__(self, phase: str, tool: str, reason: str) -> None:
        self.phase = phase
        self.tool = tool
        self.reason = reason
        super().__init__(f"tool authorization rejected: phase={phase or 'unknown'} tool={tool} reason={reason}")

    @property
    def recoverable(self) -> bool:
        """Return whether the model can safely correct the rejected arguments."""

        return self.reason in {
            "missing_write_path",
            "project_write_not_allowed",
            "harness_artifact_not_allowed",
            "write_path_outside_authority",
        }


class Tool(Protocol):
    name: str
    access: ToolAccess

    def schema(self) -> dict: ...
    def execute(self, input: dict, env: ToolEnvironment) -> str: ...


class ToolRegistry(Protocol):
    def schemas_for(self, authority: PhaseAuthority) -> list[dict]: ...
    def execute(
        self,
        name: str,
        input: dict,
        env: ToolEnvironment,
        authority: PhaseAuthority | None,
    ) -> str: ...
    def register(self, tool: Tool) -> None: ...
