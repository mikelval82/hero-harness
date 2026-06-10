from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from src.harness.tasks import task_summary
from src.integrations import telegram_api
from src.integrations.constants import PROJECT_COLORS


def compute_notify_prefix(project_name: str) -> str:
    idx = sum(ord(c) for c in project_name) % len(PROJECT_COLORS)
    return f"{PROJECT_COLORS[idx]} [{project_name}]"


def notify(msg: str, prefix: str = "") -> None:
    if prefix:
        msg = prefix + "\n" + msg
    if len(msg) > 4000:
        msg = msg[:3997] + "..."

    token = os.environ.get("TELEGRAM_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if token and chat_id:
        telegram_api.send_message(token, chat_id, msg)


def notify_result(task: str, branch: str, harness: Path, blocked_at: str = "",
                  notify_fn: Optional[callable] = None, prefix: str = "") -> None:
    if notify_fn is None:
        notify_fn = lambda msg: notify(msg, prefix=prefix)

    report_file = harness / "mission-report.md"
    if report_file.is_file():
        report_summary = "\n".join(
            report_file.read_text(encoding="utf-8").splitlines()[:60]
        )
    else:
        report_summary = ""

    summary = task_summary(harness)

    if blocked_at:
        notify_fn(f"\U0001f6ab Mission BLOCKED at {blocked_at}\nBranch: {branch}\nTask: {task}\n{summary}\n\n{report_summary}")
    else:
        tasks_data = json.loads((harness / "tasks.json").read_text(encoding="utf-8")) if (harness / "tasks.json").is_file() else []
        failed_count = sum(1 for t in tasks_data if t.get("status") == "failed")
        if failed_count > 0:
            notify_fn(f"⚠️ Mission PARTIAL\nBranch: {branch}\nTask: {task}\n{summary}\n\n{report_summary}")
        else:
            notify_fn(f"✅ Mission COMPLETE\nBranch: {branch}\nTask: {task}\n{summary}\n\n{report_summary}")


class Notifier:

    def __init__(self, prefix: str = ""):
        self.prefix = prefix

    def send(self, msg: str) -> None:
        notify(msg, prefix=self.prefix)

    def notify_result(self, task: str, branch: str, harness: Path, blocked_at: str = "") -> None:
        notify_result(task, branch, harness, blocked_at=blocked_at,
                      notify_fn=self.send)
