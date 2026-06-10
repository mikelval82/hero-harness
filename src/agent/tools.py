from __future__ import annotations

from pathlib import Path

from src.agent.tool_schema import TOOL_REGISTRY, TOOL_DEFINITIONS


class ToolExecutor:

    DEFINITIONS = TOOL_DEFINITIONS

    def __init__(self, project_dir: str | Path, harness_dir: str | Path):
        self.project_dir = Path(project_dir)
        self.harness_dir = Path(harness_dir)

    def execute(self, name: str, inp: dict) -> str:
        td = TOOL_REGISTRY.get(name)
        if td is None:
            return f"Error: unknown tool: {name}"
        try:
            return td.handler(inp, self.project_dir, self.harness_dir)
        except Exception as exc:
            return f"Error: {exc}"


def execute_tool(name: str, inp: dict, project_dir, harness_dir) -> str:
    return ToolExecutor(project_dir, harness_dir).execute(name, inp)
