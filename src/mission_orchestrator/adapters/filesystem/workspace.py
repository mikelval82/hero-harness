from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from mission_orchestrator.domain.mission import GateMode


SAFE_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def sanitize(value: str, *, max_len: int = 80) -> str:
    cleaned = SAFE_RE.sub("-", value.strip()).strip(".-")
    return (cleaned or "mission")[:max_len]


def project_id_for(project_dir: Path) -> str:
    normalized = str(project_dir.resolve()).replace("\\", "/").lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:10]


@dataclass(frozen=True)
class WorkspaceInfo:
    project_name: str
    project_id: str
    branch_safe: str
    mission_tag: str
    harness_dir: Path
    project_scope_dir: Path


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
        project_id = project_id_for(project_dir)
        branch_safe = sanitize(branch, max_len=60)
        project_key_dir = self.root / f"{project_name}-{project_id}"
        project_scope_dir = project_key_dir / "project"
        harness_dir = project_key_dir / "missions" / branch_safe
        keep = False
        if resume:
            self.validate_resume(project_dir=project_dir, branch=branch)
            keep = True
        if harness_dir.exists() and not keep:
            shutil.rmtree(harness_dir)
        harness_dir.mkdir(parents=True, exist_ok=True)
        project_scope_dir.mkdir(parents=True, exist_ok=True)
        if not keep:
            manifest = {
                "project_id": project_id,
                "project_dir": str(project_dir.resolve()),
                "branch": branch,
                "gate_mode": gate_mode.value,
                "created": datetime.now(timezone.utc).isoformat(),
            }
            (harness_dir / "_mission.json").write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
        (harness_dir / "_project_dir").write_text(str(project_dir.resolve()), encoding="utf-8")
        (harness_dir / "_gate_mode").write_text(gate_mode.value, encoding="utf-8")
        os.environ["CLAUDE_HARNESS"] = str(harness_dir)
        return WorkspaceInfo(
            project_name,
            project_id,
            branch_safe,
            f"{project_name}:{branch_safe}",
            harness_dir,
            project_scope_dir,
        )

    def validate_resume(self, *, project_dir: Path, branch: str) -> Path:
        """Require the exact existing mission before a resume can mutate it."""

        project_dir = project_dir.resolve()
        project_key_dir = self.root / f"{sanitize(project_dir.name)}-{project_id_for(project_dir)}"
        harness_dir = project_key_dir / "missions" / sanitize(branch, max_len=60)
        manifest_path = harness_dir / "_mission.json"
        if not manifest_path.is_file():
            raise RuntimeError("cannot resume: mission workspace does not exist")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("cannot resume: mission manifest is unreadable") from exc
        if Path(str(manifest.get("project_dir", ""))).resolve() != project_dir:
            raise RuntimeError("cannot resume: workspace belongs to a different project")
        if manifest.get("branch") != branch:
            raise RuntimeError("cannot resume: workspace branch does not match requested branch")
        return harness_dir
