from __future__ import annotations

from pathlib import Path
from typing import Protocol


class CodeGraphService(Protocol):
    def build(self, project_dir: Path) -> None: ...


class NoopCodeGraphService:
    def build(self, project_dir: Path) -> None:
        return None

