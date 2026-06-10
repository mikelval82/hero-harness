import json
import subprocess
import sys
import threading
from pathlib import Path

from src.harness import harness_utils
import src.integrations.telegram_api as telegram_api
from src.integrations.telegram_api import (
    TELEGRAM_MAX_MSG,
    PHASE_EMOJI,
    _msg_ctx,
)


def cmd_status(token, chat_id, _args, harness, command_queue=None, mission_state=None):
    phase_labels = {
        "brainstorm": "\U0001f50d Exploring codebase",
        "spec": "\U0001f4dd Writing specification",
        "plan": "\U0001f4d0 Planning implementation",
        "implement": "⚙️ Writing code",
        "reimplement": "\U0001f527 Fixing reviewer feedback",
        "review": "\U0001f50e Reviewing changes",
        "waiting_approval": "⏳ Waiting for YOUR approval",
        "waiting_review_decision": "⏳ Waiting for YOUR decision (retry/skip/approve)",
    }
    if mission_state is not None:
        phase = mission_state.phase or "?"
        task_num = mission_state.task_num or "?"
        task_count = mission_state.task_count or "?"
        completed = mission_state.completed
        task_id = mission_state.task_id or "-"
        task_title = mission_state.task_title or "-"
        mode = mission_state.mode or "?"
        gate = mission_state.gate or "?"
        activity = mission_state.last_activity
    else:
        state_file = harness / "_state.json"
        if not state_file.exists():
            telegram_api.send_message(token, chat_id, "No active mission state.")
            return
        state = json.loads(state_file.read_text(encoding="utf-8"))
        phase = state.get("phase", "?")
        task_num = state.get("task_num", "?")
        task_count = state.get("task_count", "?")
        completed = state.get("completed", "0")
        task_id = state.get("task_id", "-")
        task_title = state.get("task_title", "-")
        mode = state.get("mode", "?")
        gate = state.get("gate", "?")
        progress_file = harness / "_progress.txt"
        activity = progress_file.read_text(encoding="utf-8").strip() if progress_file.exists() else ""
    label = phase_labels.get(phase, phase)
    lines = [
        f"Task {task_num}/{task_count}: {task_id}",
        f"{task_title}",
        "",
        f"Phase: {label}",
        f"Completed: {completed}/{task_count}",
        f"Mode: {mode} | Gate: {gate}",
    ]
    if activity:
        lines.append(f"\nLast activity: {activity}")
    telegram_api.send_message(token, chat_id, "\n".join(lines))


def cmd_log(token, chat_id, _args, harness, command_queue=None, mission_state=None):
    log_file = harness / "mission.log"
    if not log_file.exists():
        telegram_api.send_message(token, chat_id, "No mission log found.")
        return
    lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    tail = "\n".join(lines[-30:])
    telegram_api.send_message(token, chat_id, tail or "(empty log)")


def cmd_abort(token, chat_id, _args, harness, command_queue=None, mission_state=None):
    if command_queue is not None:
        command_queue.put({"cmd": "abort"})
    else:
        (harness / "_cmd_abort").write_text("", encoding="utf-8")
    telegram_api.send_message(token, chat_id, "Abort signal sent. Mission will stop after the current phase.")


def cmd_pause(token, chat_id, _args, harness, command_queue=None, mission_state=None):
    if command_queue is not None:
        command_queue.put({"cmd": "pause"})
    else:
        (harness / "_cmd_pause").write_text("", encoding="utf-8")
    telegram_api.send_message(token, chat_id, "Mission paused. Send /resume to continue.")


def cmd_resume(token, chat_id, _args, harness, command_queue=None, mission_state=None):
    if command_queue is not None:
        command_queue.put({"cmd": "resume"})
    else:
        p = harness / "_cmd_pause"
        if p.exists():
            p.unlink()
    telegram_api.send_message(token, chat_id, "Mission resumed.")


def cmd_gate(token, chat_id, args, harness, command_queue=None, mission_state=None):
    if not args or args[0] not in ("on", "off"):
        telegram_api.send_message(token, chat_id, "Usage: /gate on | /gate off")
        return
    mode = "manual" if args[0] == "on" else "auto"
    if command_queue is not None:
        command_queue.put({"cmd": "gate", "mode": mode})
    else:
        (harness / "_gate_mode").write_text(mode, encoding="utf-8")
    label = "Manual approval enabled" if mode == "manual" else "Auto-approve enabled"
    telegram_api.send_message(token, chat_id, label)


def cmd_approve(token, chat_id, _args, harness, command_queue=None, mission_state=None):
    if command_queue is not None:
        command_queue.put({"cmd": "approve"})
    else:
        (harness / "_cmd_approve").write_text("", encoding="utf-8")
    telegram_api.send_message(token, chat_id, "Task approved.")


def cmd_reject(token, chat_id, args, harness, command_queue=None, mission_state=None):
    reason = " ".join(args) if args else ""
    if command_queue is not None:
        command_queue.put({"cmd": "reject", "reason": reason})
    else:
        (harness / "_cmd_reject").write_text(reason, encoding="utf-8")
    telegram_api.send_message(token, chat_id, f"Task rejected.{f' Reason: {reason}' if reason else ''}")


def cmd_retry(token, chat_id, args, harness, command_queue=None, mission_state=None):
    feedback = " ".join(args) if args else ""
    if command_queue is not None:
        command_queue.put({"cmd": "retry", "feedback": feedback})
    else:
        (harness / "_cmd_retry").write_text(feedback, encoding="utf-8")
    telegram_api.send_message(
        token, chat_id,
        f"Retry signal sent.{f' Your feedback: {feedback}' if feedback else ''} Reimplementing..."
    )


def cmd_skip(token, chat_id, _args, harness, command_queue=None, mission_state=None):
    if command_queue is not None:
        command_queue.put({"cmd": "skip"})
    else:
        (harness / "_cmd_skip").write_text("", encoding="utf-8")
    telegram_api.send_message(token, chat_id, "Task skipped. Continuing with next task.")


def cmd_answer(token, chat_id, args, harness, command_queue=None, mission_state=None):
    if not args:
        telegram_api.send_message(token, chat_id, "Usage: /answer <your response>")
        return
    text = " ".join(args)
    if command_queue is not None:
        command_queue.put({"cmd": "answer", "text": text})
    telegram_api.send_message(token, chat_id, f"Answer sent: {text[:100]}")


def cmd_done(token, chat_id, _args, harness, command_queue=None, mission_state=None):
    if command_queue is not None:
        command_queue.put({"cmd": "done"})
    telegram_api.send_message(token, chat_id, "Done signal sent. Grill phase will finalize.")


def cmd_verbose(token, chat_id, args, harness, command_queue=None, mission_state=None):
    n = 20
    if args and args[0].isdigit():
        n = min(int(args[0]), 50)
    progress_file = harness / "_progress.txt"
    log_file = harness / "mission.log"
    lines = []
    if log_file.exists():
        all_lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        tool_lines = [l for l in all_lines if "  > " in l]
        lines = tool_lines[-n:]
    if not lines:
        activity = progress_file.read_text(encoding="utf-8").strip() if progress_file.exists() else ""
        telegram_api.send_message(token, chat_id, activity or "No activity yet.")
        return
    telegram_api.send_message(token, chat_id, "\n".join(lines))


def _build_ask_prompt(question, harness):
    parts = [
        "You are a consultant reviewing an ongoing mission.\n"
        "Answer concisely (max 3500 chars, plain text, no markdown headers)."
    ]

    state_file = harness / "_state.json"
    if state_file.is_file():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8", errors="replace"))
            phase = state.get("phase", "unknown")
            task_id = state.get("task_id", "?")
            task_title = state.get("task_title", "")
            task_num = state.get("task_num", "?")
            task_count = state.get("task_count", "?")
            parts.append(
                f"## Mission State\n"
                f"Phase: {phase} | Task {task_num}/{task_count}: [{task_id}] {task_title}"
            )
        except (json.JSONDecodeError, OSError) as e:
            print(f"_build_ask_prompt: failed to read state: {e}", file=sys.stderr)

    artifacts = [
        ("Brainstorm", "brainstorm.md"),
        ("Spec", "spec.md"),
        ("Plan", "plan.md"),
        ("Decisions", "decisions.md"),
        ("Context", "context-hot.md"),
        ("Tasks", "tasks.json"),
    ]
    for header, filename in artifacts:
        path = harness / filename
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8", errors="replace").strip()
        if not content:
            continue
        parts.append(f"## {header}\n{content}")

    parts.append(f"Question: {question}")
    return "\n\n".join(parts)


def _run_claude_ask(prompt, harness, claude_cmd):
    project_dir = None
    pd_file = harness / "_project_dir"
    if pd_file.exists():
        pd_content = pd_file.read_text(encoding="utf-8", errors="replace").strip()
        if pd_content:
            project_dir = pd_content

    cmd = [
        claude_cmd, "-p", "-",
        "--allowedTools", "Read,Glob,Grep",
        "--add-dir", str(harness),
    ]
    if project_dir:
        cmd.extend(["--add-dir", project_dir])

    try:
        result = subprocess.run(
            cmd, input=prompt, capture_output=True, text=True, timeout=120,
        )
        return result.stdout.strip() or result.stderr.strip() or "No response generated."
    except subprocess.TimeoutExpired:
        return "Timed out waiting for response."
    except Exception as e:
        return f"Error: {e}"


def cmd_ask(token, chat_id, args, harness, claude_cmd=None):
    if not args:
        telegram_api.send_message(token, chat_id, "Usage: /ask <question>")
        return
    if not claude_cmd:
        telegram_api.send_message(token, chat_id, "Error: claude CLI not found in PATH.")
        return
    question = " ".join(args)
    telegram_api.send_message(token, chat_id, "Thinking...")

    prefix = getattr(_msg_ctx, 'prefix', '')

    def run():
        _msg_ctx.prefix = prefix
        prompt = _build_ask_prompt(question, harness)
        response = _run_claude_ask(prompt, harness, claude_cmd)
        telegram_api.send_message(token, chat_id, response)

    threading.Thread(target=run, daemon=True).start()


def cmd_read_artifact(token, chat_id, filename, harness):
    filepath = harness / filename
    if not filepath.exists():
        telegram_api.send_message(token, chat_id, f"{filename} not found.")
        return
    content = filepath.read_text(encoding="utf-8", errors="replace").strip()
    if not content:
        telegram_api.send_message(token, chat_id, f"{filename} is empty.")
        return
    header = f"--- {filename} ---\n"
    max_len = TELEGRAM_MAX_MSG - len(header) - 20
    if len(content) > max_len:
        content = content[:max_len] + "\n\n[...truncated]"
    telegram_api.send_message(token, chat_id, header + content)


def _is_pid_alive(pid):
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    import os
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def cmd_missions(token, chat_id, args, harness, command_queue=None, mission_state=None):
    missions = harness_utils.list_missions()
    if not missions:
        telegram_api.send_message(token, chat_id, "No active missions.")
        return
    dead_tags = []
    lines = []
    for tag, info in missions.items():
        pid = info.get("pid", 0)
        if pid and not _is_pid_alive(pid):
            dead_tags.append(tag)
            continue
        try:
            hp = Path(info["harness_path"])
            state = json.loads((hp / "_state.json").read_text(encoding="utf-8"))
            phase = state.get("phase", "?")
            emoji = PHASE_EMOJI.get(phase, "")
            label = f"{emoji} {phase}" if emoji else phase
            task_num = state.get("task_num", "?")
            task_count = state.get("task_count", "?")
            lines.append(f"@{tag}: {label} ({task_num}/{task_count})")
        except FileNotFoundError:
            if pid and _is_pid_alive(pid):
                lines.append(f"@{tag}: starting...")
            else:
                dead_tags.append(tag)
        except Exception:
            lines.append(f"@{tag}: error reading state")
    for tag in dead_tags:
        harness_utils.unregister_mission(tag)
    if not lines:
        telegram_api.send_message(token, chat_id, "No active missions.")
        return
    telegram_api.send_message(token, chat_id, chr(10).join(lines))


def _extract_changes_required(audit_text):
    lines = audit_text.splitlines()
    in_changes = False
    result = []
    for line in lines:
        if "Cambios Requeridos" in line or "Changes Required" in line:
            in_changes = True
            continue
        if in_changes and line.startswith("#"):
            break
        if in_changes and line.strip():
            result.append(line)
    if result:
        return "What needs fixing:\n" + "\n".join(result)
    return audit_text[:2000]


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
}

COMMANDS = {
    "/status": cmd_status,
    "/log": cmd_log,
    "/verbose": cmd_verbose,
    "/abort": cmd_abort,
    "/pause": cmd_pause,
    "/resume": cmd_resume,
    "/gate": cmd_gate,
    "/approve": cmd_approve,
    "/reject": cmd_reject,
    "/retry": cmd_retry,
    "/skip": cmd_skip,
    "/answer": cmd_answer,
    "/done": cmd_done,
    "/missions": cmd_missions,
}

HELP_TEXT = (
    "Available commands:\n"
    "\n-- Control --\n"
    "/status — current phase, task, progress\n"
    "/missions — active missions (tag, phase, progress)\n"
    "/log — last 30 lines of mission log\n"
    "/verbose [N] — last N tool calls (default 20, max 50)\n"
    "/abort — stop mission after current phase\n"
    "/pause — pause between phases\n"
    "/resume — resume paused mission\n"
    "/gate on|off — toggle manual approval\n"
    "/approve — approve current task\n"
    "/reject [reason] — reject current task\n"
    "/retry [feedback] — retry with reviewer feedback + your input\n"
    "/skip — skip failed task, continue with next\n"
    "/answer <text> — respond to grill question\n"
    "/done — finalize grill phase\n"
    "/ask <question> — ask Claude about the mission/code\n"
    "\n-- Artifacts --\n"
    "/brief — mission brief (from alignment)\n"
    "/brainstorm — analysis and approaches\n"
    "/tasks — task list (tasks.json)\n"
    "/spec — current task specification\n"
    "/plan — implementation plan\n"
    "/decisions — technical decisions\n"
    "/statusfile — implementation status\n"
    "/audit — reviewer verdict\n"
    "/warm — compressed context (prior tasks)\n"
    "/hot — current task context\n"
    "\n-- Multi-mission --\n"
    "Append @tag to direct a command to a\n"
    "specific mission: /status@project:fix-auth\n"
    "Without @tag, commands target the\n"
    "first active mission."
)
