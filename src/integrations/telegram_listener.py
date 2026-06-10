#!/usr/bin/env python3
"""Telegram listener for mission.sh bidirectional control.

Usage: python3 telegram_listener.py <TOKEN> <CHAT_ID>
Runs until killed (SIGTERM). Communicates with mission.sh via signal files.
"""
import json
import shutil
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from src.harness import harness_utils
import src.integrations.telegram_api as telegram_api
from src.integrations.telegram_commands import (
    cmd_ask,
    cmd_read_artifact,
    _extract_changes_required,
    COMMANDS,
    ARTIFACT_COMMANDS,
    HELP_TEXT,
)

HARNESS = None
CLAUDE_CMD = None


@dataclass
class MissionState:
    phase: str = ""
    task_id: str = ""
    task_title: str = ""
    task_num: int = 0
    task_count: int = 0
    completed: int = 0
    mode: str = "full"
    gate: str = "auto"
    last_activity: str = ""
    waiting_approval: dict | None = None
    waiting_notified: bool = False


def resolve_harness(tag):
    missions = harness_utils.list_missions()
    if tag:
        if tag in missions:
            p = Path(missions[tag]["harness_path"])
            if p.is_dir():
                return p, tag
        for t, m in missions.items():
            project = t.split(":")[0] if ":" in t else t
            if project == tag:
                p = Path(m["harness_path"])
                if p.is_dir():
                    return p, t
    for t, m in missions.items():
        p = Path(m["harness_path"])
        if p.is_dir():
            return p, t
    return HARNESS, None


def handle_command(token, chat_id, text, harness, command_queue=None, mission_state=None):
    if not text.startswith("/"):
        return
    parts = text.split()
    raw_cmd = parts[0].lower()
    cmd = raw_cmd.split("@")[0]
    args = parts[1:]
    if "@" in raw_cmd:
        _, tag = raw_cmd.split("@", 1)
    elif args and args[0].startswith("@"):
        tag = args[0][1:]
        args = args[1:]
    else:
        tag = None
    harness, resolved_tag = resolve_harness(tag)
    telegram_api._set_msg_prefix(resolved_tag)

    if cmd == "/ask":
        cmd_ask(token, chat_id, args, harness, claude_cmd=CLAUDE_CMD)
        return
    if cmd in ("/help", "/start"):
        telegram_api.send_message(token, chat_id, HELP_TEXT)
        return
    if cmd in ARTIFACT_COMMANDS:
        cmd_read_artifact(token, chat_id, ARTIFACT_COMMANDS[cmd], harness)
        return
    handler = COMMANDS.get(cmd)
    if handler:
        handler(token, chat_id, args, harness, command_queue=command_queue, mission_state=mission_state)
    else:
        telegram_api.send_message(token, chat_id, f"Unknown command: {cmd}\n\n{HELP_TEXT}")


def check_waiting_approval(token, chat_id, command_queue=None, mission_state=None):
    if mission_state is not None:
        if mission_state.waiting_approval is None or mission_state.waiting_notified:
            return
        info = mission_state.waiting_approval
        verdict = info.get("verdict", "?")
        task_id = info.get("task_id", "?")
        task_title = info.get("task_title", "?")
        if verdict == "CHANGES_REQUESTED":
            msg = (
                f"Task {task_id}: {task_title}\n"
                f"Reviewer: CHANGES REQUESTED\n\n"
                "Options:\n"
                "/retry [your feedback] — reimplement with fixes\n"
                "/skip — skip this task, continue\n"
                "/approve — force-approve anyway\n"
                "/abort — stop mission"
            )
        else:
            msg = (
                f"Review complete: {task_id} — {task_title}\n"
                f"Verdict: {verdict}\n\n"
                "Reply /approve or /reject [reason]"
            )
        telegram_api.send_message(token, chat_id, msg)
        mission_state.waiting_notified = True
        return
    missions = harness_utils.list_missions()
    tagged_paths = [(tag, Path(m["harness_path"])) for tag, m in missions.items() if Path(m["harness_path"]).is_dir()] if missions else []
    if not tagged_paths:
        tagged_paths = [(None, HARNESS)]
    for tag, hp in tagged_paths:
        telegram_api._set_msg_prefix(tag)
        waiting = hp / "_waiting_approval"
        notified = hp / "_waiting_notified"
        if waiting.exists() and not notified.exists():
            try:
                info = json.loads(waiting.read_text(encoding="utf-8"))
                audit_file = hp / "audit.md"
                audit = ""
                if audit_file.exists():
                    audit = audit_file.read_text(encoding="utf-8", errors="replace")[:3000]
                verdict = info.get("verdict", "?")
                task_id = info.get("task_id", "?")
                task_title = info.get("task_title", "?")

                if verdict == "CHANGES_REQUESTED":
                    changes = _extract_changes_required(audit)
                    msg = (
                        f"Task {task_id}: {task_title}\n"
                        f"Reviewer: CHANGES REQUESTED\n\n"
                        f"{changes}\n\n"
                        "Options:\n"
                        "/retry [your feedback] — reimplement with fixes\n"
                        "/skip — skip this task, continue\n"
                        "/approve — force-approve anyway\n"
                        "/abort — stop mission"
                    )
                else:
                    msg = (
                        f"Review complete: {task_id} — {task_title}\n"
                        f"Verdict: {verdict}\n\n"
                        f"{audit}\n\n"
                        "Reply /approve or /reject [reason]"
                    )
                telegram_api.send_message(token, chat_id, msg)
                notified.write_text("", encoding="utf-8")
            except Exception as e:
                print(f"check_waiting_approval error: {e}", file=sys.stderr)


def poll_loop(token, chat_id, harness, command_queue=None, mission_state=None):
    offset = 0
    while True:
        updates = telegram_api.get_updates(token, offset, timeout=30)
        for update in updates:
            offset = update["update_id"] + 1
            msg = update.get("message", {})
            if str(msg.get("chat", {}).get("id")) != chat_id:
                continue
            text = msg.get("text", "").strip()
            if text:
                handle_command(token, chat_id, text, harness, command_queue=command_queue, mission_state=mission_state)
        check_waiting_approval(token, chat_id, command_queue=command_queue, mission_state=mission_state)


def start_listener(token, chat_id, command_queue, mission_state, harness=None):
    global CLAUDE_CMD
    if CLAUDE_CMD is None:
        CLAUDE_CMD = shutil.which("claude")
    t = threading.Thread(
        target=poll_loop,
        args=(token, chat_id, harness or Path("/tmp/claude-harness")),
        kwargs={"command_queue": command_queue, "mission_state": mission_state},
        daemon=True,
    )
    t.start()
    return t


def main():
    global HARNESS, CLAUDE_CMD
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <TELEGRAM_TOKEN> <CHAT_ID> [HARNESS_PATH]", file=sys.stderr)
        sys.exit(1)
    HARNESS = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("/tmp/claude-harness")
    CLAUDE_CMD = shutil.which("claude")
    if not CLAUDE_CMD:
        print("WARNING: claude CLI not found in PATH, /ask will not work", file=sys.stderr)
    poll_loop(sys.argv[1], sys.argv[2], HARNESS)


if __name__ == "__main__":
    main()
