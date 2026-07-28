from __future__ import annotations

from pathlib import Path

from src.agent.path_policy import _validate_capability_write_path
from src.agent.tool_schema import TOOL_REGISTRY, TOOL_DEFINITIONS


class ToolExecutor:

    DEFINITIONS = TOOL_DEFINITIONS

    def __init__(
        self,
        project_dir: str | Path,
        harness_dir: str | Path,
        *,
        allow_project_writes: bool = False,
    ):
        self.project_dir = Path(project_dir)
        self.harness_dir = Path(harness_dir)
        self.allow_project_writes = allow_project_writes

    def execute(self, name: str, inp: dict) -> str:
        td = TOOL_REGISTRY.get(name)
        if td is None:
            return f"Error: unknown tool: {name}"
        try:
            dispatch_input = dict(inp)
            if name in {"Write", "Edit"}:
                resolved = _validate_capability_write_path(
                    dispatch_input["file_path"],
                    self.project_dir,
                    self.harness_dir,
                    allow_project_writes=self.allow_project_writes,
                )
                dispatch_input["file_path"] = str(resolved)
            return td.handler(dispatch_input, self.project_dir, self.harness_dir)
        except Exception as exc:
            return f"Error: {exc}"


def execute_tool(
    name: str,
    inp: dict,
    project_dir,
    harness_dir,
    *,
    allow_project_writes: bool = False,
) -> str:
    return ToolExecutor(
        project_dir,
        harness_dir,
        allow_project_writes=allow_project_writes,
    ).execute(name, inp)
