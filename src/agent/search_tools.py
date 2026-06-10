from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from src.agent.path_policy import _validate_access_path, _git_visible_files


GLOB_SCHEMA: dict = {
    "name": "Glob",
    "description": "Find files matching a glob pattern. Results sorted by modification time (newest first).",
    "input_schema": {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Glob pattern to match files"},
            "path": {"type": "string", "description": "Directory to search in (default: project root)"},
        },
        "required": ["pattern"],
    },
}

GREP_SCHEMA: dict = {
    "name": "Grep",
    "description": "Search file contents using regex. Uses ripgrep if available, falls back to re module.",
    "input_schema": {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Regex pattern to search for"},
            "path": {"type": "string", "description": "File or directory to search in"},
            "glob": {"type": "string", "description": "Glob pattern to filter files"},
            "output_mode": {
                "type": "string",
                "description": "Output mode: files_with_matches (default), content, or count",
                "enum": ["files_with_matches", "content", "count"],
            },
            "context": {"type": "integer", "description": "Lines of context around matches"},
            "head_limit": {"type": "integer", "description": "Max output lines (default 250)"},
        },
        "required": ["pattern"],
    },
}


def _tool_glob(inp: dict, project_dir: Path, harness_dir: Path) -> str:
    search_root = (
        _validate_access_path(inp["path"], project_dir, harness_dir)
        if "path" in inp else project_dir
    )
    visible = _git_visible_files(search_root)
    if visible is not None:
        from fnmatch import fnmatch
        pattern = inp["pattern"]
        matched = [search_root / f for f in visible if fnmatch(f, pattern)]
        matched = [p for p in matched if p.is_file()]
    else:
        matched = [p for p in search_root.glob(inp["pattern"]) if p.is_file()]
    matched.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return "\n".join(str(p.relative_to(search_root)) for p in matched)


def _tool_grep(inp: dict, project_dir: Path, harness_dir: Path) -> str:
    pattern = inp["pattern"]
    search_path = str(_validate_access_path(inp.get("path", str(project_dir)), project_dir, harness_dir))
    glob_filter = inp.get("glob")
    output_mode = inp.get("output_mode", "files_with_matches")
    context = inp.get("context")
    head_limit = inp.get("head_limit", 250)

    if shutil.which("rg"):
        args = ["rg", pattern]
        if output_mode == "files_with_matches":
            args.append("-l")
        elif output_mode == "count":
            args.append("-c")
        if context is not None:
            args.extend(["-C", str(context)])
        if glob_filter:
            args.extend(["--glob", glob_filter])
        args.append(search_path)
        try:
            result = subprocess.run(
                args, capture_output=True, text=True, timeout=30
            )
        except subprocess.TimeoutExpired:
            return "Error: grep timed out"
        output = result.stdout
    else:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_grep_fallback, pattern, search_path, glob_filter, output_mode, context)
            try:
                output = future.result(timeout=30)
            except concurrent.futures.TimeoutError:
                return "Error: grep timed out"

    lines = output.splitlines()
    if len(lines) > head_limit:
        lines = lines[:head_limit]
    return "\n".join(lines)


def _grep_fallback(
    pattern: str,
    search_path: str,
    glob_filter: str | None,
    output_mode: str,
    context: int | None,
) -> str:
    regex = re.compile(pattern)
    root = Path(search_path)
    results: list[str] = []

    if root.is_file():
        files = [root]
    else:
        visible = _git_visible_files(root)
        if visible is not None:
            from fnmatch import fnmatch
            pat = glob_filter or "*"
            files = sorted(root / f for f in visible if fnmatch(f, pat))
        else:
            files = sorted(root.rglob(glob_filter or "*"))

    for fpath in files:
        if not fpath.is_file():
            continue
        try:
            lines = fpath.read_text(encoding="utf-8", errors="strict").splitlines()
        except (UnicodeDecodeError, PermissionError):
            continue
        match_lines = [(i, line) for i, line in enumerate(lines, 1) if regex.search(line)]
        if not match_lines:
            continue

        rel = str(fpath.relative_to(root)) if fpath != root else fpath.name

        if output_mode == "files_with_matches":
            results.append(rel)
        elif output_mode == "count":
            results.append(f"{rel}:{len(match_lines)}")
        else:
            ctx = context or 0
            for lineno, line in match_lines:
                if ctx > 0:
                    start = max(0, lineno - 1 - ctx)
                    end = min(len(lines), lineno + ctx)
                    for ci in range(start, end):
                        prefix = "-" if ci != lineno - 1 else ":"
                        results.append(f"{rel}{prefix}{ci + 1}{prefix}{lines[ci]}")
                    results.append("--")
                else:
                    results.append(f"{rel}:{lineno}:{line}")

    return "\n".join(results)
