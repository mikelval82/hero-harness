from __future__ import annotations

import subprocess
from pathlib import Path


def _git_visible_files(root: Path) -> set[str] | None:
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            capture_output=True, text=True, timeout=10, cwd=str(root),
        )
        if result.returncode != 0:
            return None
        if not result.stdout.strip():
            return None
        return set(result.stdout.splitlines())
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _resolve_tool_path(file_path: str, project_dir: Path) -> Path:
    path = Path(file_path)
    if not path.is_absolute():
        path = project_dir / path
    return path.resolve()


def _validate_access_path(file_path: str, project_dir: Path, harness_dir: Path) -> Path:
    resolved = _resolve_tool_path(file_path, project_dir)
    proj = project_dir.resolve()
    harness = harness_dir.resolve()
    if resolved == proj or resolved.is_relative_to(proj):
        return resolved
    if resolved == harness or resolved.is_relative_to(harness):
        return resolved
    raise ValueError(
        f"path {resolved} is outside allowed directories "
        f"({proj}, {harness})"
    )


def _validate_write_path(file_path: str, project_dir: Path, harness_dir: Path) -> Path:
    return _validate_access_path(file_path, project_dir, harness_dir)
