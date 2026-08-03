from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ToolEnvironment:
    project_dir: Path
    harness_dir: Path


class Tool(Protocol):
    name: str

    def schema(self) -> dict: ...
    def execute(self, input: dict, env: ToolEnvironment) -> str: ...


class ToolRegistry(Protocol):
    def schemas_for(self, names: list[str] | tuple[str, ...]) -> list[dict]: ...
    def execute(self, name: str, input: dict, env: ToolEnvironment) -> str: ...
    def register(self, tool: Tool) -> None: ...

