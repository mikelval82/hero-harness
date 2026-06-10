from __future__ import annotations

import hashlib
import shutil
from pathlib import Path


MEMORY_ROOT = ".harness-memory"
MEMORY_FILE = "PROJECT_MEMORY.md"
HARNESS_MEMORY_FILE = "project-memory.md"
HARNESS_MEMORY_PATH_FILE = "_project_memory_path"


def _sanitize(value: str, max_len: int = 40) -> str:
    safe = "".join(ch for ch in value.replace("/", "-").replace("\\", "-") if ch.isalnum() or ch in "-_")
    safe = safe or "project"
    return safe[:max_len]


def project_memory_key(project_dir: str | Path) -> str:
    resolved = str(Path(project_dir).resolve())
    digest = hashlib.sha1(resolved.lower().encode("utf-8")).hexdigest()[:10]
    return f"{_sanitize(Path(resolved).name)}-{digest}"


def project_memory_dir(project_dir: str | Path, *, base_dir: Path | None = None) -> Path:
    root = base_dir if base_dir is not None else Path.home() / MEMORY_ROOT
    return root / project_memory_key(project_dir)


def project_memory_path(project_dir: str | Path, *, base_dir: Path | None = None) -> Path:
    return project_memory_dir(project_dir, base_dir=base_dir) / MEMORY_FILE


def default_project_memory(project_dir: str | Path) -> str:
    resolved = Path(project_dir).resolve()
    return (
        "# Project Memory\n\n"
        f"- project_name: {resolved.name}\n"
        f"- project_dir: {resolved}\n\n"
        "## Policy\n\n"
        "- Store only durable, repo-specific conventions, commands, constraints, and recurring failure modes.\n"
        "- Keep entries evidence-backed: cite a file, test command, artifact, or mission result when possible.\n"
        "- Do not store secrets, credentials, private user conversation, transient branch notes, or generic coding advice.\n"
        "- Prefer short bullets that will help the next mission avoid repeated exploration or repeated mistakes.\n\n"
        "## Conventions\n\n"
        "- none recorded yet\n\n"
        "## Validation Commands\n\n"
        "- none recorded yet\n\n"
        "## Recurring Failure Modes\n\n"
        "- none recorded yet\n"
    )


def ensure_project_memory(project_dir: str | Path, *, base_dir: Path | None = None) -> Path:
    path = project_memory_path(project_dir, base_dir=base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        path.write_text(default_project_memory(project_dir), encoding="utf-8")
    return path


def stage_project_memory(
    project_dir: str | Path,
    harness: Path,
    *,
    base_dir: Path | None = None,
    preserve_existing: bool = False,
) -> dict[str, Path]:
    persistent = ensure_project_memory(project_dir, base_dir=base_dir)
    staged = harness / HARNESS_MEMORY_FILE
    if not preserve_existing or not staged.is_file():
        shutil.copy2(persistent, staged)
    (harness / HARNESS_MEMORY_PATH_FILE).write_text(str(persistent), encoding="utf-8")
    return {"persistent": persistent, "staged": staged}


def sync_project_memory(harness: Path) -> bool:
    staged = harness / HARNESS_MEMORY_FILE
    pointer = harness / HARNESS_MEMORY_PATH_FILE
    if not staged.is_file() or not pointer.is_file():
        return False
    raw_persistent = pointer.read_text(encoding="utf-8").strip()
    if not raw_persistent:
        return False
    persistent = Path(raw_persistent)
    persistent.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(staged, persistent)
    return True
