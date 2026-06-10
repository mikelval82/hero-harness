from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

from src.core.paths import SRC_DIR, PROMPTS_DIR
from src.core.block_state import BlockKind, BlockReason
from src.agent.tool_schema import TOOL_DEFINITIONS
from src.agent import loop as agent_loop
from src.core.context import PHASE_REGISTRY, PhaseName
from src.core.git import detect_base_branch
from src.core.model_policy import select_model_for_phase
from src.core.notification import notify
from src.harness.prompt_renderer import render_prompt
from src.harness.phase_logger import make_tool_callback, _write_metric
from src.harness.tasks import task_summary as _task_summary
from src.harness.telemetry import TOKEN_BUDGET_ENV, format_cost_summary, parse_token_budget
from typing import Optional, Callable


def _consolidate_tasks(client, *, harness, harness_win, project_dir, max_tasks, log=None):
    tasks_path = harness / "tasks.json"
    backup_path = harness / "_tasks_backup.json"

    shutil.copy2(tasks_path, backup_path)

    user_prompt = render_prompt(
        str(PROMPTS_DIR / "consolidate-prompt.md"),
        {"MAX_TASKS": str(max_tasks)},
        {},
        harness_win,
    )

    tools = [t for t in TOOL_DEFINITIONS if t["name"] in {"Read", "Write"}]
    model_selection = select_model_for_phase("consolidate")
    if log:
        log(f"Model: {model_selection.model} ({model_selection.tier}, {model_selection.reason})")

    try:
        phase_result = agent_loop.run_phase(
            client,
            system_prompt="",
            user_prompt=user_prompt,
            tools=tools,
            phase_name="consolidate",
            project_dir=project_dir,
            harness_dir=harness,
            on_tool_call=make_tool_callback(harness),
            on_log=log,
            timeout=PHASE_REGISTRY[PhaseName.CONSOLIDATE].timeout,
            model=model_selection.model,
        )
        if phase_result is not None:
            _write_metric(
                harness,
                "consolidate",
                turns=phase_result.turns,
                elapsed=phase_result.elapsed,
                input_tokens=phase_result.input_tokens,
                output_tokens=phase_result.output_tokens,
                model=phase_result.model,
                result="success",
            )
        else:
            _write_metric(harness, "consolidate", model=model_selection.model, result="success")
    except (agent_loop.PhaseTimeout, agent_loop.MaxTurnsExceeded, agent_loop.MaxRetriesExceeded) as exc:
        result = {
            agent_loop.PhaseTimeout: "timeout",
            agent_loop.MaxTurnsExceeded: "max_turns",
            agent_loop.MaxRetriesExceeded: "api_retries",
        }.get(type(exc), "failed")
        metrics = {"model": model_selection.model, **(getattr(exc, "metrics", None) or {})}
        _write_metric(harness, "consolidate", **metrics, result=result)
        if log:
            log(f"Consolidation failed ({type(exc).__name__}), restoring backup")
        shutil.copy2(backup_path, tasks_path)
        backup_path.unlink(missing_ok=True)
        return

    try:
        new_tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        if log:
            log("Consolidation produced invalid JSON, restoring backup")
        shutil.copy2(backup_path, tasks_path)
        backup_path.unlink(missing_ok=True)
        return

    if not isinstance(new_tasks, list) or not all(
        isinstance(t, dict) and "id" in t and "title" in t for t in new_tasks
    ):
        if log:
            log("Consolidation produced invalid task schema, restoring backup")
        shutil.copy2(backup_path, tasks_path)
        backup_path.unlink(missing_ok=True)
        return

    if len(new_tasks) > max_tasks:
        if log:
            log(f"Consolidation still has {len(new_tasks)} tasks (limit {max_tasks}), continuing anyway")

    backup_path.unlink(missing_ok=True)
    if log:
        log(f"Consolidation done: {len(new_tasks)} tasks")


def generate_report(client, *, task, branch, mode, harness, harness_win, project_dir, blocked, log=None):
    if log:
        log(">>> Generating report")

    tasks_status = _task_summary(harness)
    token_budget = parse_token_budget(os.environ.get(TOKEN_BUDGET_ENV))
    token_cost_summary = format_cost_summary(harness, token_budget=token_budget)
    if log:
        log(token_cost_summary)
    else:
        print(token_cost_summary)

    if blocked.reason:
        result = blocked.value
    else:
        tasks_data = json.loads((harness / "tasks.json").read_text(encoding="utf-8")) if (harness / "tasks.json").is_file() else []
        failed_count = sum(1 for t in tasks_data if t.get("status") == "failed")
        if failed_count > 0:
            result = f"PARTIAL — {tasks_status}"
        else:
            result = "ALL TASKS APPROVED"

    config = PHASE_REGISTRY[PhaseName.REPORT] if mode == "full" else PHASE_REGISTRY[PhaseName.REPORT_PLAN]

    variables = {
        "TASK": task, "BRANCH": branch, "MODE": mode, "RESULT": result,
        "TASKS_STATUS": tasks_status,
        "TOKEN_COST_SUMMARY": token_cost_summary,
    }
    if mode == "full":
        base_branch = detect_base_branch()
        log_result = subprocess.run(
            ["git", "log", "--oneline", branch, "--not", base_branch],
            capture_output=True, text=True,
        )
        variables["GIT_EVIDENCE"] = "\n".join(log_result.stdout.splitlines()[:20]) if log_result.stdout else ""
        diff_result = subprocess.run(
            ["git", "diff", "--stat", f"{base_branch}...{branch}"],
            capture_output=True, text=True,
        )
        variables["GIT_DIFF_STAT"] = "\n".join(diff_result.stdout.splitlines()[-5:]) if diff_result.stdout else ""

    template = str(PROMPTS_DIR / config.template)
    tool_names = set(config.tools.split(","))
    tools = [t for t in TOOL_DEFINITIONS if t["name"] in tool_names]
    includes = {
        "PROJECT_MEMORY": str(harness / "project-memory.md"),
        "RETRIEVED_SKILLS": str(harness / "retrieved-skills.md"),
    }
    user_prompt = render_prompt(template, variables, includes, harness_win)
    model_selection = select_model_for_phase(config.name, mode=mode)
    if log:
        log(f"Model: {model_selection.model} ({model_selection.tier}, {model_selection.reason})")

    try:
        phase_result = agent_loop.run_phase(
            client,
            system_prompt="",
            user_prompt=user_prompt,
            tools=tools,
            phase_name=config.name,
            project_dir=project_dir,
            harness_dir=harness,
            on_tool_call=make_tool_callback(harness),
            on_log=log,
            timeout=config.timeout,
            max_turns=config.max_turns,
            model=model_selection.model,
        )
        _write_metric(
            harness,
            config.name,
            turns=phase_result.turns,
            elapsed=phase_result.elapsed,
            input_tokens=phase_result.input_tokens,
            output_tokens=phase_result.output_tokens,
            model=phase_result.model,
            result="success",
        )
    except agent_loop.PhaseTimeout as exc:
        metrics = {"model": model_selection.model, **(getattr(exc, "metrics", None) or {})}
        _write_metric(harness, config.name, **metrics, result="timeout")
        blocked.reason = BlockReason(BlockKind.TIMEOUT, phase="report")
        return
    except agent_loop.MaxTurnsExceeded as exc:
        metrics = {"model": model_selection.model, **(getattr(exc, "metrics", None) or {})}
        _write_metric(harness, config.name, **metrics, result="max_turns")
        blocked.reason = BlockReason(BlockKind.MAX_TURNS, phase="report")
        return
    except agent_loop.MaxRetriesExceeded as exc:
        metrics = {"model": model_selection.model, **(getattr(exc, "metrics", None) or {})}
        _write_metric(harness, config.name, **metrics, result="api_retries")
        blocked.reason = BlockReason(BlockKind.API_RETRIES, phase="report")
        return

    if log:
        log("<<< Report generated")


_notify_result_backend: Optional[Callable] = None


def set_notify_result_backend(fn: Callable) -> None:
    global _notify_result_backend
    _notify_result_backend = fn


def notify_result(task, branch, harness, blocked):
    if _notify_result_backend is not None:
        _notify_result_backend(task, branch, harness, blocked_at=blocked.value,
                               notify_fn=notify)


def build_code_graph(project_dir, log=None):
    script = SRC_DIR / "analysis" / "code_graph.py"
    try:
        result = subprocess.run(
            [sys.executable, str(script), "build", project_dir],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            if log:
                log(f"code_graph: {result.stdout.strip()}")
        else:
            if log:
                log(f"code_graph build failed (rc={result.returncode}): {result.stderr[:300]}")
    except subprocess.TimeoutExpired:
        if log:
            log("code_graph build timed out (120s) — skipping")
    except Exception as exc:
        if log:
            log(f"code_graph build error: {exc}")
