from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from mission_orchestrator.domain.mission import GateMode


SAFE_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def sanitize(value: str, *, max_len: int = 80) -> str:
    cleaned = SAFE_RE.sub("-", value.strip()).strip(".-")
    return (cleaned or "mission")[:max_len]


@dataclass(frozen=True)
class WorkspaceInfo:
    project_name: str
    branch_safe: str
    mission_tag: str
    harness_dir: Path


class WorkspaceManager:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or (Path.home() / ".harness")

    def setup(
        self,
        *,
        project_dir: Path,
        branch: str,
        resume: bool,
        gate_mode: GateMode,
    ) -> WorkspaceInfo:
        project_name = sanitize(project_dir.name)
        branch_safe = sanitize(branch, max_len=60)
        harness_dir = self.root / project_name / branch_safe
        keep = resume and (harness_dir / "tasks.json").exists()
        if harness_dir.exists() and not keep:
            shutil.rmtree(harness_dir)
        harness_dir.mkdir(parents=True, exist_ok=True)
        (harness_dir / "_project_dir").write_text(str(project_dir.resolve()), encoding="utf-8")
        (harness_dir / "_gate_mode").write_text(gate_mode.value, encoding="utf-8")
        os.environ["CLAUDE_HARNESS"] = str(harness_dir)
        return WorkspaceInfo(project_name, branch_safe, f"{project_name}:{branch_safe}", harness_dir)

