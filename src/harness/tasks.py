from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from src.core.context import TASK_PIPELINES


def _parse_files_section(text: str) -> list[str]:
    in_files = False
    result = []
    for line in text.splitlines():
        if re.match(r"^#+\s*[Ff]iles", line):
            in_files = True
            continue
        if in_files and re.match(r"^#+\s", line):
            break
        if in_files:
            f = line.strip().lstrip("-").strip().strip("`").strip()
            if f:
                result.append(f)
    return result


def parse_status_files(harness: Path) -> list[str]:
    status = harness / "status.md"
    if not status.is_file():
        return []
    text = status.read_text(encoding="utf-8")
    return _parse_files_section(text)


def load_tasks(harness: Path) -> list[dict]:
    tasks_path = harness / "tasks.json"
    if not tasks_path.is_file():
        return []
    return json.loads(tasks_path.read_text(encoding="utf-8"))


def update_task(index: int, status: str, harness: Path, reason: str = "") -> None:
    tasks_path = harness / "tasks.json"
    tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
    if index < 0 or index >= len(tasks):
        raise ValueError(f"task index {index} out of range (len={len(tasks)})")
    tasks[index]["status"] = status
    if reason:
        tasks[index]["failure_reason"] = reason
    tasks_path.write_text(json.dumps(tasks, indent=2), encoding="utf-8")


def task_complexity(task: dict) -> str:
    complexity = task.get("complexity", "M")
    return complexity if complexity in TASK_PIPELINES else "M"


def task_complexity_reason(task: dict) -> str:
    reason = str(task.get("complexity_reason", "")).strip()
    if reason:
        return reason
    raw_complexity = task.get("complexity")
    if raw_complexity is None:
        return "complexity missing; defaulted to M standard route"
    if raw_complexity not in TASK_PIPELINES:
        return f"unknown complexity {raw_complexity!r}; defaulted to M standard route"
    return f"complexity={raw_complexity} selected without explicit complexity_reason"


def _task_counts(tasks: list[dict]) -> tuple[int, int, int, int]:
    total = len(tasks)
    completed = sum(1 for t in tasks if t.get("status") == "completed")
    failed = sum(1 for t in tasks if t.get("status") == "failed")
    pending = sum(1 for t in tasks if t.get("status", "pending") == "pending")
    return total, completed, failed, pending


def task_summary(harness: Path) -> str:
    tasks = load_tasks(harness)
    if not tasks:
        tasks_path = harness / "tasks.json"
        if not tasks_path.is_file():
            return "No tasks.json found"
    total, completed, failed, pending = _task_counts(tasks)
    lines = [f"Total: {total} | Completed: {completed} | Failed: {failed} | Pending: {pending}"]
    for t in tasks:
        lines.append(
            f"  ROUTE [{t['id']}]: {task_complexity(t)} - {task_complexity_reason(t)}"
        )
        if t.get("status") == "failed" and t.get("failure_reason"):
            lines.append(f"  FAILED [{t['id']}]: {t['failure_reason']}")
    return "\n".join(lines)


def task_listing(harness: Path) -> str:
    tasks = load_tasks(harness)
    if not tasks:
        tasks_path = harness / "tasks.json"
        if not tasks_path.is_file():
            return "No tasks.json found"
    total, completed, failed, pending = _task_counts(tasks)
    lines = [
        "TASK STATUS (from tasks.json - source of truth):",
        f"Total: {total} | Completed: {completed} | Failed: {failed} | Pending: {pending}",
    ]
    for t in tasks:
        s = t.get("status", "pending").upper()
        lines.append(
            f'  [{s}] {t["id"]}: {t["title"]} '
            f'(complexity={task_complexity(t)}; reason={task_complexity_reason(t)})'
        )
    return "\n".join(lines)


def is_mission_abort(blocked_at: str) -> bool:
    if not blocked_at:
        return False
    return blocked_at == "user_abort" or blocked_at.startswith("signal_")


def audit_verdict(harness: Path) -> str:
    audit = harness / "audit.md"
    if not audit.is_file():
        return "UNKNOWN"
    text = audit.read_text(encoding="utf-8")
    m = re.search(r"APPROVED|MINOR_CHANGES|CHANGES_REQUESTED", text)
    return m.group(0) if m else "UNKNOWN"


def stage_task_files(harness: Path) -> None:
    files = parse_status_files(harness)
    if not files:
        print("WARNING: no files to stage")
        return
    for f in files:
        if Path(f).is_file():
            subprocess.run(["git", "add", f], check=False)
            print(f"Staged: {f}")
