from __future__ import annotations

from pathlib import Path

from src.agent.path_policy import _validate_access_path, _validate_write_path


READ_SCHEMA: dict = {
    "name": "Read",
    "description": "Read a file from the filesystem. Returns contents with line numbers.",
    "input_schema": {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Absolute path to the file to read"},
            "offset": {"type": "integer", "description": "1-based line number to start reading from"},
            "limit": {"type": "integer", "description": "Number of lines to read"},
        },
        "required": ["file_path"],
    },
}

WRITE_SCHEMA: dict = {
    "name": "Write",
    "description": "Write content to a file. Creates parent directories if needed.",
    "input_schema": {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Absolute path to the file to write"},
            "content": {"type": "string", "description": "Content to write to the file"},
        },
        "required": ["file_path", "content"],
    },
}

EDIT_SCHEMA: dict = {
    "name": "Edit",
    "description": "Replace a string in a file. By default requires exactly one match.",
    "input_schema": {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Absolute path to the file to edit"},
            "old_string": {"type": "string", "description": "The text to find and replace"},
            "new_string": {"type": "string", "description": "The replacement text"},
            "replace_all": {"type": "boolean", "description": "Replace all occurrences instead of requiring exactly one"},
        },
        "required": ["file_path", "old_string", "new_string"],
    },
}


def _tool_read(inp: dict, project_dir: Path, harness_dir: Path) -> str:
    path = _validate_access_path(inp["file_path"], project_dir, harness_dir)
    if not path.exists():
        return f"Error: file not found: {path}"
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    offset = inp.get("offset", 1)
    if offset < 1:
        offset = 1
    start_idx = offset - 1
    limit = inp.get("limit")
    if limit is not None:
        end_idx = start_idx + limit
        lines = lines[start_idx:end_idx]
    else:
        lines = lines[start_idx:]
    formatted = []
    for i, line in enumerate(lines, start=offset):
        formatted.append(f"{i:6}\t{line}")
    return "\n".join(formatted)


def _tool_write(inp: dict, project_dir: Path, harness_dir: Path) -> str:
    resolved = _validate_write_path(inp["file_path"], project_dir, harness_dir)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(inp["content"], encoding="utf-8")
    return f"Successfully wrote to {resolved}"


def _tool_edit(inp: dict, project_dir: Path, harness_dir: Path) -> str:
    resolved = _validate_write_path(inp["file_path"], project_dir, harness_dir)
    if not resolved.exists():
        return f"Error: file not found: {resolved}"
    content = resolved.read_text(encoding="utf-8", errors="replace")
    old_string = inp["old_string"]
    new_string = inp["new_string"]
    replace_all = inp.get("replace_all", False)
    count = content.count(old_string)
    if count == 0:
        return f"Error: old_string not found in {resolved}"
    if count > 1 and not replace_all:
        return f"Error: old_string found {count} times, use replace_all=True"
    if replace_all:
        new_content = content.replace(old_string, new_string)
    else:
        new_content = content.replace(old_string, new_string, 1)
    resolved.write_text(new_content, encoding="utf-8")
    replacements = count if replace_all else 1
    return f"Replaced {replacements} occurrence(s) in {resolved}"
