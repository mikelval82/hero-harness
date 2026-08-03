from __future__ import annotations

from mission_orchestrator.adapters.tools.bash_executor import BashTool
from mission_orchestrator.adapters.tools.bash_policy import BashPolicy
from mission_orchestrator.adapters.tools.file_tools import EditTool, ReadTool, WriteTool
from mission_orchestrator.adapters.tools.graph_tools import GraphProposeTool, GraphQueryTool
from mission_orchestrator.adapters.tools.path_policy import PathPolicy
from mission_orchestrator.adapters.tools.search_tools import GlobTool, GrepTool
from mission_orchestrator.ports.logger import MissionLogger
from mission_orchestrator.ports.tool_registry import Tool, ToolEnvironment


class LocalToolRegistry:
    def __init__(self, logger: MissionLogger | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        self.logger = logger

    def schemas_for(self, names: list[str] | tuple[str, ...]) -> list[dict]:
        return [self._tools[name].schema() for name in names if name in self._tools]

    def execute(self, name: str, input: dict, env: ToolEnvironment) -> str:
        if name not in self._tools:
            raise KeyError(f"unknown tool: {name}")
        if self.logger:
            self.logger.tool_call(name, input)
        return self._tools[name].execute(input, env)

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool


def default_tool_registry(logger: MissionLogger | None = None) -> LocalToolRegistry:
    path_policy = PathPolicy()
    registry = LocalToolRegistry(logger)
    registry.register(ReadTool(path_policy))
    registry.register(WriteTool(path_policy))
    registry.register(EditTool(path_policy))
    registry.register(GlobTool(path_policy))
    registry.register(GrepTool(path_policy))
    registry.register(BashTool(BashPolicy(path_policy)))
    registry.register(GraphQueryTool())
    registry.register(GraphProposeTool())
    return registry

