#!/usr/bin/env python3
"""Harness CLI dispatch and setup for mission.sh orchestration.

Subcommands:
  render-prompt [--agent <agent.md>] <template.md> KEY=VALUE ...
  task-info <index>
  task-count
  update-task <index> <status>
  task-summary
  parse-files <status.md>
  register-mission <tag> <harness_path> <pid>
  unregister-mission <tag>
  list-missions
  refiner-proposal [harness_path] [min_recurrence]
"""
import json
import os
import re
import shutil
import sys
from pathlib import Path

from src.core.paths import HARNESS
from src.harness import tasks
from src.harness.registry import (
    REGISTRY_PATH,
    register_mission,
    unregister_mission,
    list_missions,
)
from src.harness.prompt_renderer import (
    PromptRenderer,
    render_prompt,
    load_agent_system,
    strip_frontmatter,
    _DEFAULT_WORKSPACE_FOOTER,
)
from src.harness.project_memory import stage_project_memory
from src.harness.case_base import stage_retrieved_cases
from src.harness.skill_library import stage_retrieved_skills
from src.harness.refiner import write_refiner_proposal


def _shell_escape(value: str) -> str:
    value = value.replace(chr(92), chr(92) + chr(92))
    value = value.replace("$", chr(92) + "$")
    value = value.replace("`", chr(92) + "`")
    value = value.replace('"', chr(92) + '"')
    value = value.replace("\n", " ")
    value = value.replace("\r", "")
    return value


def sanitize_name(name: str, max_len: int = 0) -> str:
    name = name.replace('/', '-')
    name = re.sub(r'[^a-zA-Z0-9_-]', '', name)
    if max_len > 0:
        name = name[:max_len]
    return name


def setup_harness(branch: str, gate: bool, cwd=None, resume: bool = False, task: str = "") -> dict:
    cwd = Path(cwd or Path.cwd()).resolve()
    branch_safe = sanitize_name(branch, max_len=60)
    project_name = sanitize_name(cwd.name)
    mission_tag = f"{project_name}:{branch_safe}"

    harness = Path.home() / '.harness' / project_name / branch_safe
    harness_win = str(harness.resolve())
    preserving_harness = resume and harness.exists() and (harness / "tasks.json").is_file()

    if preserving_harness:
        pass
    else:
        if harness.exists():
            shutil.rmtree(harness)
        harness.mkdir(parents=True)

    (harness / '_project_dir').write_text(str(cwd), encoding='utf-8')
    (harness / '_gate_mode').write_text('manual' if gate else 'auto', encoding='utf-8')
    memory_info = stage_project_memory(cwd, harness, preserve_existing=preserving_harness)
    cases_info = stage_retrieved_cases(cwd, harness, query=task, preserve_existing=preserving_harness)
    skills_info = stage_retrieved_skills(cwd, harness, query=task, preserve_existing=preserving_harness)

    os.environ['CLAUDE_HARNESS'] = harness_win

    return {
        'harness': harness,
        'harness_win': harness_win,
        'mission_tag': mission_tag,
        'project_name': project_name,
        'branch_safe': branch_safe,
        'project_memory_path': memory_info['persistent'],
        'project_memory_harness': memory_info['staged'],
        'project_cases_path': cases_info['persistent'],
        'retrieved_cases_harness': cases_info['staged'],
        'project_skills_path': skills_info['persistent'],
        'retrieved_skills_harness': skills_info['staged'],
        'generated_skills_harness': skills_info['generated'],
    }


# --- CLI subcommand handlers ---


def cmd_render_prompt(args):
    agent_file = None
    harness_path = os.environ.get("CLAUDE_HARNESS", "/tmp/claude-harness")
    positional = []
    variables = {}
    includes = {}
    i = 0
    while i < len(args):
        if args[i] == "--agent" and i + 1 < len(args):
            agent_file = Path(args[i + 1])
            i += 2
        elif args[i] == "--harness-path" and i + 1 < len(args):
            harness_path = args[i + 1]
            i += 2
        elif args[i] == "--include" and i + 1 < len(args):
            key, filepath = args[i + 1].split("=", 1)
            includes[key] = filepath
            i += 2
        elif "=" in args[i] and not args[i].startswith("-"):
            key, value = args[i].split("=", 1)
            variables[key] = value
            i += 1
        else:
            positional.append(args[i])
            i += 1

    user_prompt = render_prompt(Path(positional[0]), variables, includes, harness_path)

    if agent_file:
        agent_body = strip_frontmatter(agent_file.read_text(encoding="utf-8"))
        agent_body = agent_body.replace("$CLAUDE_HARNESS", harness_path)
        footer = _DEFAULT_WORKSPACE_FOOTER.format(path=harness_path)
        print(f"{agent_body}\n\n---\n\n## Mission context\n\n{user_prompt}{footer}")
    else:
        print(user_prompt)


def cmd_task_info(args):
    index = int(args[0])
    task_items = json.loads((HARNESS / "tasks.json").read_text(encoding="utf-8"))
    task = task_items[index]
    tid = _shell_escape(task["id"])
    title = _shell_escape(task["title"])
    status = _shell_escape(task.get("status", "pending"))
    complexity = _shell_escape(tasks.task_complexity(task))
    complexity_reason = _shell_escape(tasks.task_complexity_reason(task))
    print(f'TASK_ID="{tid}"')
    print(f'TASK_TITLE="{title}"')
    print(f'TASK_STATUS="{status}"')
    print(f'TASK_COMPLEXITY="{complexity}"')
    print(f'TASK_COMPLEXITY_REASON="{complexity_reason}"')


def cmd_task_count(args):
    tasks = json.loads((HARNESS / "tasks.json").read_text(encoding="utf-8"))
    print(len(tasks))


def cmd_update_task(args):
    tasks.update_task(int(args[0]), args[1], HARNESS)


def cmd_task_summary(args):
    print(tasks.task_listing(HARNESS))


def cmd_parse_files(args):
    text = Path(args[0]).read_text(encoding="utf-8")
    for f in tasks._parse_files_section(text):
        print(f)


def cmd_register_mission(args):
    if len(args) != 3:
        print("Usage: register-mission <tag> <harness_path> <pid>", file=sys.stderr)
        sys.exit(1)
    register_mission(args[0], args[1], int(args[2]))


def cmd_unregister_mission(args):
    if len(args) != 1:
        print("Usage: unregister-mission <tag>", file=sys.stderr)
        sys.exit(1)
    unregister_mission(args[0])


def cmd_list_missions(args):
    print(json.dumps(list_missions(), indent=2))


def cmd_refiner_proposal(args):
    harness = Path(args[0]) if args else HARNESS
    min_recurrence = int(args[1]) if len(args) > 1 else 2
    path = write_refiner_proposal(harness, min_recurrence=min_recurrence)
    print(f"Refiner proposal written: {path}")
    print("No prompts, agents, code, tests, memory, cases, or skills were modified.")


COMMANDS = {
    "render-prompt": cmd_render_prompt,
    "task-info": cmd_task_info,
    "task-count": cmd_task_count,
    "update-task": cmd_update_task,
    "task-summary": cmd_task_summary,
    "parse-files": cmd_parse_files,
    "register-mission": cmd_register_mission,
    "unregister-mission": cmd_unregister_mission,
    "list-missions": cmd_list_missions,
    "refiner-proposal": cmd_refiner_proposal,
}

if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"Usage: {sys.argv[0]} <{'|'.join(COMMANDS)}> [args...]", file=sys.stderr)
        sys.exit(1)
    COMMANDS[sys.argv[1]](sys.argv[2:])
