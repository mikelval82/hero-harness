from __future__ import annotations

from pathlib import Path

from mission_orchestrator.adapters.tools.bash_executor import BashTool
from mission_orchestrator.adapters.tools.bash_policy import BashPolicy
from mission_orchestrator.adapters.tools.file_tools import EditTool, ReadTool, WriteJsonTool, WriteTool
from mission_orchestrator.adapters.tools.graph_tools import CodeGraphTool, GraphProposeTool, GraphQueryTool
from mission_orchestrator.adapters.tools.path_policy import PathPolicy
from mission_orchestrator.adapters.tools.search_tools import GlobTool, GrepTool
from mission_orchestrator.adapters.tools.validation_runner import RunValidationTool
from mission_orchestrator.domain.phase import PhaseAuthority
from mission_orchestrator.ports.logger import MissionLogger
from mission_orchestrator.ports.tool_registry import (
    Tool,
    ToolAccess,
    ToolAuthorizationError,
    ToolEnvironment,
)


def _is_inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


class LocalToolRegistry:
    def __init__(
        self,
        logger: MissionLogger | None = None,
        *,
        path_policy: PathPolicy | None = None,
    ) -> None:
        self._tools: dict[str, Tool] = {}
        self.logger = logger
        self.path_policy = path_policy or PathPolicy()

    def schemas_for(self, authority: PhaseAuthority) -> list[dict]:
        schemas: list[dict] = []
        for name in authority.tools:
            tool = self._tools.get(name)
            if tool is None:
                self._deny(authority, name, "tool_unregistered")
            self._authorize_access(authority, tool)
            schemas.append(tool.schema())
        return schemas

    def execute(
        self,
        name: str,
        input: dict,
        env: ToolEnvironment,
        authority: PhaseAuthority | None,
    ) -> str:
        if authority is None:
            self._deny(None, name, "missing_authority")
        tool = self._tools.get(name)
        if tool is None:
            self._deny(authority, name, "tool_unregistered")
        if name not in authority.tools:
            self._deny(authority, name, "tool_not_allowed")
        execution_env = self._authorize_execution(authority, tool, input, env)
        if self.logger:
            self.logger.tool_call(name, input)
        return tool.execute(input, execution_env)

    def register(self, tool: Tool) -> None:
        if not isinstance(getattr(tool, "access", None), ToolAccess):
            raise TypeError(f"tool {getattr(tool, 'name', '<unknown>')} has no declared access class")
        self._tools[tool.name] = tool

    def _authorize_execution(
        self,
        authority: PhaseAuthority,
        tool: Tool,
        input: dict,
        env: ToolEnvironment,
    ) -> ToolEnvironment:
        self._authorize_access(authority, tool)
        if tool.access == ToolAccess.PATH_WRITE:
            self._authorize_write_path(authority, tool.name, input, env)
        if tool.access == ToolAccess.PROJECT_EXECUTION:
            # Implementation may run bounded project commands, but not use the
            # process tool to access arbitrary HARNESS artifacts.
            return ToolEnvironment(env.project_dir, env.project_dir)
        return env

    def _authorize_access(self, authority: PhaseAuthority, tool: Tool) -> None:
        if tool.access == ToolAccess.PROJECT_EXECUTION and not authority.allow_project_writes:
            self._deny(authority, tool.name, "project_execution_not_allowed")
        if (
            tool.access == ToolAccess.HARNESS_MUTATION
            and tool.name not in authority.harness_mutation_tools
        ):
            self._deny(authority, tool.name, "harness_mutation_not_allowed")

    def _authorize_write_path(
        self,
        authority: PhaseAuthority,
        tool_name: str,
        input: dict,
        env: ToolEnvironment,
    ) -> None:
        raw_path = input.get("file_path")
        if not isinstance(raw_path, str) or not raw_path:
            self._deny(authority, tool_name, "missing_write_path")
        path = self.path_policy.resolve(raw_path, env)
        project = env.project_dir.resolve()
        harness = env.harness_dir.resolve()
        if _is_inside(path, harness):
            relative = path.relative_to(harness).as_posix()
            if relative not in authority.harness_write_paths:
                self._deny(authority, tool_name, "harness_artifact_not_allowed")
            return
        if _is_inside(path, project):
            if not authority.allow_project_writes:
                self._deny(authority, tool_name, "project_write_not_allowed")
            return
        self._deny(authority, tool_name, "write_path_outside_authority")

    def _deny(
        self,
        authority: PhaseAuthority | None,
        tool: str,
        reason: str,
    ) -> None:
        phase = authority.phase.value if authority is not None else ""
        if self.logger:
            try:
                self.logger.metric(
                    {
                        "event": "tool_rejected",
                        "phase": phase,
                        "tool": tool,
                        "reason": reason,
                    }
                )
            except Exception:
                pass
        raise ToolAuthorizationError(phase, tool, reason)


def default_tool_registry(logger: MissionLogger | None = None) -> LocalToolRegistry:
    path_policy = PathPolicy()
    registry = LocalToolRegistry(logger, path_policy=path_policy)
    registry.register(ReadTool(path_policy))
    registry.register(WriteTool(path_policy))
    registry.register(WriteJsonTool(path_policy))
    registry.register(EditTool(path_policy))
    registry.register(GlobTool(path_policy))
    registry.register(GrepTool(path_policy))
    registry.register(BashTool(BashPolicy(path_policy)))
    registry.register(RunValidationTool())
    registry.register(CodeGraphTool())
    registry.register(GraphQueryTool())
    registry.register(GraphProposeTool())
    return registry
