from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from src.agent.file_tools import (
    READ_SCHEMA, _tool_read,
    WRITE_SCHEMA, _tool_write,
    EDIT_SCHEMA, _tool_edit,
)
from src.agent.bash_executor import BASH_SCHEMA, _tool_bash
from src.agent.search_tools import GLOB_SCHEMA, _tool_glob, GREP_SCHEMA, _tool_grep


@dataclass
class ToolDef:
    schema: dict
    handler: Callable


TOOL_REGISTRY: dict[str, ToolDef] = {
    "Read": ToolDef(schema=READ_SCHEMA, handler=_tool_read),
    "Write": ToolDef(schema=WRITE_SCHEMA, handler=_tool_write),
    "Edit": ToolDef(schema=EDIT_SCHEMA, handler=_tool_edit),
    "Bash": ToolDef(schema=BASH_SCHEMA, handler=_tool_bash),
    "Glob": ToolDef(schema=GLOB_SCHEMA, handler=_tool_glob),
    "Grep": ToolDef(schema=GREP_SCHEMA, handler=_tool_grep),
}

TOOL_DEFINITIONS: list[dict] = [td.schema for td in TOOL_REGISTRY.values()]


def register_tool(name: str, schema: dict, handler: Callable) -> None:
    TOOL_REGISTRY[name] = ToolDef(schema=schema, handler=handler)
    TOOL_DEFINITIONS.clear()
    TOOL_DEFINITIONS.extend(td.schema for td in TOOL_REGISTRY.values())
