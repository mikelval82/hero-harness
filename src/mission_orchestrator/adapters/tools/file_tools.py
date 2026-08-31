from __future__ import annotations

from dataclasses import dataclass

from mission_orchestrator.adapters.tools.path_policy import PathPolicy
from mission_orchestrator.ports.tool_registry import ToolAccess, ToolEnvironment


def _schema(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "name": name,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
    }


@dataclass
class ReadTool:
    policy: PathPolicy
    name: str = "Read"
    access: ToolAccess = ToolAccess.READ_ONLY

    def schema(self) -> dict:
        return _schema(
            self.name,
            "Read a UTF-8 file with line numbers.",
            {
                "file_path": {"type": "string"},
                "offset": {"type": "integer"},
                "limit": {"type": "integer"},
            },
            ["file_path"],
        )

    def execute(self, input: dict, env: ToolEnvironment) -> str:
        path = self.policy.validate_access_path(str(input["file_path"]), env)
        offset = max(1, int(input.get("offset", 1) or 1))
        limit = input.get("limit")
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        selected = lines[offset - 1 :]
        if limit is not None:
            selected = selected[: max(0, int(limit))]
        return "\n".join(f"{offset + index}: {line}" for index, line in enumerate(selected))


@dataclass
class WriteTool:
    policy: PathPolicy
    name: str = "Write"
    access: ToolAccess = ToolAccess.PATH_WRITE

    def schema(self) -> dict:
        return _schema(
            self.name,
            "Write a UTF-8 file, creating parent directories.",
            {"file_path": {"type": "string"}, "content": {"type": "string"}},
            ["file_path", "content"],
        )

    def execute(self, input: dict, env: ToolEnvironment) -> str:
        path = self.policy.validate_write_path(str(input["file_path"]), env)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(input.get("content", "")), encoding="utf-8")
        return f"Wrote {path}"


@dataclass
class EditTool:
    policy: PathPolicy
    name: str = "Edit"
    access: ToolAccess = ToolAccess.PATH_WRITE

    def schema(self) -> dict:
        return _schema(
            self.name,
            "Replace text in a UTF-8 file.",
            {
                "file_path": {"type": "string"},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"},
                "replace_all": {"type": "boolean"},
            },
            ["file_path", "old_string", "new_string"],
        )

    def execute(self, input: dict, env: ToolEnvironment) -> str:
        path = self.policy.validate_write_path(str(input["file_path"]), env)
        old = str(input["old_string"])
        new = str(input.get("new_string", ""))
        replace_all = bool(input.get("replace_all", False))
        text = path.read_text(encoding="utf-8")
        count = text.count(old)
        if count == 0:
            raise ValueError("old_string not found")
        if count > 1 and not replace_all:
            raise ValueError("old_string has multiple matches; set replace_all=true")
        path.write_text(text.replace(old, new, -1 if replace_all else 1), encoding="utf-8")
        return f"Edited {path} ({count if replace_all else 1} replacement(s))"
