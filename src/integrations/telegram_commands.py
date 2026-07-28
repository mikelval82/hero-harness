"""Read-only Telegram commands for the mission owned by the listener.

Mutating commands are intentionally handled by :class:`CommandRouter`; this
module only renders mission state/artifacts and bridges ``/ask`` to the
read-only internal LLM service.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from pathlib import Path

from src.core.state import ControlState, MissionState
from src.integrations import telegram_api
from src.integrations.code_questions import CodeQuestionService


PHASE_LABELS = {
    "research": "🔎 Exploring codebase",
    "brainstorm": "🔎 Exploring codebase",
    "structure": "🧱 Structuring tasks",
    "grill": "❓ Clarifying requirements",
    "spec": "📝 Writing specification",
    "plan": "🗺️ Planning implementation",
    "implement": "⚙️ Writing code",
    "implement_bursts": "⚙️ Writing code",
    "reimplement": "🔧 Fixing reviewer feedback",
    "review": "🔍 Reviewing changes",
    "report": "📋 Writing mission report",
}


def _reject_extra_args(token: str, chat_id: str, args: list[str], usage: str) -> bool:
    if not args:
        return False
    telegram_api.send_message(token, chat_id, f"Usage: {usage}")
    return True


def _state_snapshot(mission_state: MissionState | None, harness: Path) -> dict:
    if mission_state is not None:
        return mission_state.snapshot()
    path = harness / "_state.json"
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return state if isinstance(state, dict) else {}


def cmd_status(
    token: str,
    chat_id: str,
    args: list[str],
    harness: Path,
    *,
    mission_state: MissionState | None = None,
) -> None:
    if _reject_extra_args(token, chat_id, args, "/status"):
        return
    state = _state_snapshot(mission_state, harness)
    if not state:
        telegram_api.send_message(token, chat_id, "No active mission state yet.")
        return

    phase = str(state.get("phase") or "?")
    control = str(state.get("control_state") or ControlState.RUNNING.value)
    interaction = state.get("interaction")
    label = PHASE_LABELS.get(phase, phase)
    if isinstance(interaction, dict):
        label = f"Waiting for {interaction.get('kind', 'input')}"
    elif control == ControlState.PAUSE_PENDING.value:
        label = f"{label} (pause requested)"
    elif control == ControlState.PAUSED.value:
        label = "Paused"
    elif control == ControlState.ABORT_PENDING.value:
        label = f"{label} (abort requested)"

    task_num = state.get("task_num") or "?"
    task_count = state.get("task_count") or "?"
    task_id = state.get("task_id") or "-"
    task_title = state.get("task_title") or "-"
    completed = state.get("completed", 0)
    mode = state.get("mode") or "?"
    gate = state.get("gate") or "?"
    activity = str(state.get("last_activity") or "").strip()
    if not activity:
        progress = harness / "_progress.txt"
        try:
            activity = progress.read_text(encoding="utf-8").strip()
        except OSError:
            activity = ""

    lines = [
        f"Task {task_num}/{task_count}: {task_id}",
        str(task_title),
        "",
        f"Phase: {label}",
        f"Control: {control}",
        f"Completed: {completed}/{task_count}",
        f"Mode: {mode} | Gate: {gate}",
    ]
    if activity:
        lines.extend(("", f"Last activity: {activity}"))
    telegram_api.send_message(token, chat_id, "\n".join(lines))


def cmd_log(
    token: str,
    chat_id: str,
    args: list[str],
    harness: Path,
    *,
    mission_state: MissionState | None = None,
) -> None:
    del mission_state
    if _reject_extra_args(token, chat_id, args, "/log"):
        return
    log_file = harness / "mission.log"
    if not log_file.is_file():
        telegram_api.send_message(token, chat_id, "No mission log found.")
        return
    lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    telegram_api.send_message(token, chat_id, "\n".join(lines[-30:]) or "(empty log)")


def cmd_verbose(
    token: str,
    chat_id: str,
    args: list[str],
    harness: Path,
    *,
    mission_state: MissionState | None = None,
) -> None:
    del mission_state
    if len(args) != 1 or not args[0].isdigit() or not 1 <= int(args[0]) <= 50:
        telegram_api.send_message(token, chat_id, "Usage: /verbose <1-50>")
        return
    count = int(args[0])
    log_file = harness / "mission.log"
    lines: list[str] = []
    if log_file.is_file():
        all_lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        lines = [line for line in all_lines if "  > " in line][-count:]
    if lines:
        telegram_api.send_message(token, chat_id, "\n".join(lines))
        return
    progress = harness / "_progress.txt"
    try:
        activity = progress.read_text(encoding="utf-8").strip()
    except OSError:
        activity = ""
    telegram_api.send_message(token, chat_id, activity or "No activity yet.")


def cmd_read_artifact(
    token: str,
    chat_id: str,
    args: list[str],
    filename: str,
    harness: Path,
) -> None:
    if _reject_extra_args(token, chat_id, args, f"/{Path(filename).stem}"):
        return
    filepath = harness / filename
    if not filepath.is_file():
        telegram_api.send_message(token, chat_id, f"{filename} not found.")
        return
    content = filepath.read_text(encoding="utf-8", errors="replace").strip()
    if not content:
        telegram_api.send_message(token, chat_id, f"{filename} is empty.")
        return
    header = f"--- {filename} ---\n"
    marker = "\n\n[...truncated; open the workspace artifact for the full content]"
    available = telegram_api.TELEGRAM_MAX_MSG - len(header) - len(marker)
    if len(content) > available:
        boundary = telegram_api._safe_chunk_boundary(content, available)
        content = content[:boundary] + marker
    telegram_api.send_message(token, chat_id, header + content)


def cmd_ask(
    token: str,
    chat_id: str,
    args: list[str],
    service: CodeQuestionService,
    *,
    mission_state: MissionState | None = None,
    delivery_allowed: Callable[[], bool] | None = None,
) -> None:
    if mission_state is not None and mission_state.control_state in {
        ControlState.ABORT_PENDING,
        ControlState.ABORTED,
    }:
        telegram_api.send_message(token, chat_id, "Code questions are disabled after abort is requested.")
        return

    # CodeQuestionService can complete very quickly in tests. Buffer a callback
    # until the acceptance decision is known so "Thinking..." never arrives
    # after the final answer.
    guard = threading.Lock()
    pending: list[str] = []
    decided = False

    def deliver(message: str) -> None:
        nonlocal decided
        if delivery_allowed is not None and not delivery_allowed():
            return
        with guard:
            if not decided:
                pending.append(message)
                return
        if delivery_allowed is not None and not delivery_allowed():
            return
        telegram_api.send_message(token, chat_id, message)

    accepted = service.ask(" ".join(args), deliver)
    try:
        if accepted and (delivery_allowed is None or delivery_allowed()):
            telegram_api.send_message(token, chat_id, "Thinking...")
    finally:
        with guard:
            decided = True
            buffered = list(pending)
            pending.clear()
    for message in buffered:
        if delivery_allowed is None or delivery_allowed():
            telegram_api.send_message(token, chat_id, message)


ARTIFACT_COMMANDS = {
    "/brief": "brief.md",
    "/plan": "plan.md",
    "/decisions": "decisions.md",
    "/spec": "spec.md",
    "/audit": "audit.md",
    "/statusfile": "status.md",
    "/brainstorm": "brainstorm.md",
    "/tasks": "tasks.json",
    "/hot": "context-hot.md",
    "/warm": "context-cold.md",
    "/report": "mission-report.md",
}

READ_COMMANDS = {
    "/status": cmd_status,
    "/log": cmd_log,
    "/verbose": cmd_verbose,
}

MUTATING_COMMANDS = frozenset(
    {
        "/pause",
        "/resume",
        "/abort",
        "/gate",
        "/answer",
        "/done",
        "/approve",
        "/reject",
        "/retry",
        "/skip",
    }
)

HELP_TEXT = """Available commands (current mission only):

-- Read --
/status — current phase, task, control state and progress
/log — last 30 lines of the mission log
/verbose <1-50> — recent tool calls
/ask <question> — read-only question about the mission/code

-- Control (availability depends on current state) --
/pause — request a pause at the next safe checkpoint
/resume — cancel a pending pause or resume a paused mission
/abort — stop at the next safe checkpoint
/gate on|off — change future approval gates
/answer <text> | /done — answer the active grill question
/approve | /reject [reason] — decide an active approval
/retry [feedback] | /skip | /approve — decide requested changes

-- Artifacts --
/brief /brainstorm /tasks /spec /plan /decisions
/statusfile /audit /report /warm /hot

Commands also accept Telegram's standard /command@BotUsername form.
There is no mission selection: this bot controls only its owning mission."""
