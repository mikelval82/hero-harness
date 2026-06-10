from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from src.agent.path_policy import _validate_access_path
from src.agent.bash_policy import _validate_bash_command


BASH_SCHEMA: dict = {
    "name": "Bash",
    "description": "Execute a shell command. Only whitelisted commands are allowed.",
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The shell command to execute"},
            "timeout": {"type": "integer", "description": "Timeout in seconds (default 120, max 600)"},
        },
        "required": ["command"],
    },
}


@dataclass
class _CommandResult:
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0
    cwd: Path | None = None


def _tool_bash(inp: dict, project_dir: Path, harness_dir: Path) -> str:
    command = inp["command"]
    pipelines = _validate_bash_command(command, project_dir, harness_dir)
    timeout = min(inp.get("timeout", 120), 600)
    env = os.environ.copy()
    cwd = project_dir.resolve()
    output = []
    last_code = 0
    try:
        for operator, pipeline in pipelines:
            if operator == "&&" and last_code != 0:
                continue
            if operator == "||" and last_code == 0:
                continue
            result = _run_bash_pipeline(pipeline, cwd, env, project_dir, harness_dir, timeout)
            if result.cwd is not None:
                cwd = result.cwd
            output.append(result.stdout)
            output.append(result.stderr)
            last_code = result.returncode
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout}s"
    output_text = "".join(output)
    if last_code != 0:
        output_text += f"\nExit code: {last_code}"
    return output_text


def _run_bash_pipeline(
    pipeline: list[list[str]],
    cwd: Path,
    env: dict[str, str],
    project_dir: Path,
    harness_dir: Path,
    timeout: int,
) -> _CommandResult:
    stdin_text = ""
    stderr = []
    result = _CommandResult()
    current_cwd = cwd
    for argv in pipeline:
        result = _run_bash_command(argv, stdin_text, current_cwd, env, project_dir, harness_dir, timeout)
        if result.cwd is not None:
            current_cwd = result.cwd
        stdin_text = result.stdout
        if result.stderr:
            stderr.append(result.stderr)
    result.stderr = "".join(stderr)
    if current_cwd != cwd:
        result.cwd = current_cwd
    return result


def _run_bash_command(
    argv: list[str],
    stdin_text: str,
    cwd: Path,
    env: dict[str, str],
    project_dir: Path,
    harness_dir: Path,
    timeout: int,
) -> _CommandResult:
    command = Path(argv[0]).name
    args = argv[1:]
    if command == "cd":
        target = args[0] if args else str(project_dir)
        resolved = _validate_access_path(str(cwd / target), project_dir, harness_dir)
        if not resolved.is_dir():
            return _CommandResult(stderr=f"cd: no such directory: {target}\n", returncode=1)
        return _CommandResult(cwd=resolved)
    if command == "export":
        for assignment in args:
            if "=" in assignment:
                key, value = assignment.split("=", 1)
                env[key] = value
        return _CommandResult()
    if command == "echo":
        return _CommandResult(stdout=" ".join(args) + "\n")
    if command == "true":
        return _CommandResult()
    if command == "false":
        return _CommandResult(returncode=1)
    if command == "cat":
        return _builtin_cat(args, stdin_text, cwd, project_dir, harness_dir)
    if command == "head":
        return _builtin_head_tail(args, stdin_text, cwd, project_dir, harness_dir, tail=False)
    if command == "tail":
        return _builtin_head_tail(args, stdin_text, cwd, project_dir, harness_dir, tail=True)
    if command == "ls":
        return _builtin_ls(args, cwd, project_dir, harness_dir)

    try:
        completed = subprocess.run(
            argv,
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd),
            env=env,
        )
    except FileNotFoundError:
        return _CommandResult(stderr=f"command not found: {argv[0]}\n", returncode=127)
    return _CommandResult(completed.stdout, completed.stderr, completed.returncode)


def _builtin_cat(
    args: list[str],
    stdin_text: str,
    cwd: Path,
    project_dir: Path,
    harness_dir: Path,
) -> _CommandResult:
    files = [arg for arg in args if not arg.startswith("-")]
    if not files:
        return _CommandResult(stdout=stdin_text)
    output = []
    for file_arg in files:
        path = _validate_access_path(str(cwd / file_arg), project_dir, harness_dir)
        if not path.is_file():
            return _CommandResult(stderr=f"cat: {file_arg}: No such file\n", returncode=1)
        output.append(path.read_text(encoding="utf-8", errors="replace"))
    return _CommandResult(stdout="".join(output))


def _line_limit(args: list[str], default: int = 10) -> int:
    if "-n" in args:
        idx = args.index("-n")
        if idx + 1 < len(args):
            try:
                return max(0, int(args[idx + 1]))
            except ValueError:
                return default
    for arg in args:
        if arg.startswith("-n") and len(arg) > 2:
            try:
                return max(0, int(arg[2:]))
            except ValueError:
                return default
    return default


def _builtin_head_tail(
    args: list[str],
    stdin_text: str,
    cwd: Path,
    project_dir: Path,
    harness_dir: Path,
    *,
    tail: bool,
) -> _CommandResult:
    limit = _line_limit(args)
    files = [arg for arg in args if not arg.startswith("-") and arg != str(limit)]
    if files:
        cat_result = _builtin_cat(files, "", cwd, project_dir, harness_dir)
        if cat_result.returncode != 0:
            return cat_result
        text = cat_result.stdout
    else:
        text = stdin_text
    lines = text.splitlines()
    selected = lines[-limit:] if tail else lines[:limit]
    return _CommandResult(stdout="\n".join(selected) + ("\n" if selected else ""))


def _builtin_ls(args: list[str], cwd: Path, project_dir: Path, harness_dir: Path) -> _CommandResult:
    paths = [arg for arg in args if not arg.startswith("-")] or ["."]
    output = []
    for path_arg in paths:
        path = _validate_access_path(str(cwd / path_arg), project_dir, harness_dir)
        if path.is_dir():
            output.extend(sorted(child.name for child in path.iterdir()))
        elif path.exists():
            output.append(path.name)
        else:
            return _CommandResult(stderr=f"ls: cannot access '{path_arg}'\n", returncode=1)
    return _CommandResult(stdout="\n".join(output) + ("\n" if output else ""))
