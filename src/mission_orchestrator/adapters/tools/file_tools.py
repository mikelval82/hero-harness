from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

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
        if path.name in {"tasks.json", "review-evidence.json"}:
            raise ValueError(f"{path.name} requires the WriteJson tool")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(input.get("content", "")), encoding="utf-8")
        return f"Wrote {path}"


@dataclass
class WriteJsonTool:
    """Write a JSON artifact only after validating its required envelope."""

    policy: PathPolicy
    name: str = "WriteJson"
    access: ToolAccess = ToolAccess.PATH_WRITE

    def schema(self) -> dict:
        return _schema(
            self.name,
            "Write a validated JSON artifact. Use this for tasks.json and review-evidence.json.",
            {"file_path": {"type": "string"}, "content": {"type": "string"}},
            ["file_path", "content"],
        )

    def execute(self, input: dict, env: ToolEnvironment) -> str:
        path = self.policy.validate_write_path(str(input["file_path"]), env)
        content = str(input.get("content", ""))
        try:
            value = json.loads(content)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid JSON: {error.msg} at character {error.pos}") from error
        self._validate_artifact(path, value)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return f"Wrote validated JSON {path}"

    @staticmethod
    def _validate_artifact(path: Path, value: object) -> None:
        if path.name == "tasks.json":
            if not isinstance(value, list):
                raise ValueError("tasks.json must contain a JSON list")
            required = {"id", "title", "complexity", "status", "failure_reason", "covers", "dependencies", "target_nodes"}
            for index, item in enumerate(value):
                if not isinstance(item, dict):
                    raise ValueError(f"tasks.json item {index} must be an object")
                missing = sorted(required - item.keys())
                extra = sorted(item.keys() - required)
                if missing or extra:
                    details = []
                    if missing:
                        details.append(f"missing fields: {', '.join(missing)}")
                    if extra:
                        details.append(f"unexpected fields: {', '.join(extra)}")
                    raise ValueError(f"tasks.json item {index} " + "; ".join(details))
                if not isinstance(item["id"], str) or not item["id"].strip():
                    raise ValueError(f"tasks.json item {index} id must be a non-empty string")
                if not isinstance(item["title"], str) or not item["title"].strip():
                    raise ValueError(f"tasks.json item {index} title must be a non-empty string")
                for field in ("covers", "dependencies", "target_nodes"):
                    if not isinstance(item[field], list):
                        raise ValueError(f"tasks.json item {index} {field} must be a list")
        elif path.name == "review-evidence.json":
            from mission_orchestrator.application.review_evidence import ReviewEvidence

            ReviewEvidence.from_json(json.dumps(value))


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
