from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import Path

from mission_orchestrator.adapters.tools.path_policy import PathPolicy
from mission_orchestrator.ports.tool_registry import ToolEnvironment


FORBIDDEN_PATTERNS = (r"`", r"\$\(", r"<\(", r">\(", r"<<")
PIPE = "|"
CONTROL_OPERATORS = {"&&", "||"}
REDIRECTION_CHARS = {"<", ">"}
ALLOWLIST = {
    "python3", "python", "git", "wc", "sort", "grep", "awk", "sed", "jq", "file", "diff",
    "tr", "cut", "uniq", "tee", "find", "mkdir", "cp", "mv", "rm", "touch", "chmod",
    "printf", "test", "read", "cd", "export", "echo", "true", "false", "cat", "head", "tail", "ls",
}
WRITE_COMMANDS = {"mkdir", "cp", "mv", "rm", "touch", "chmod", "tee"}


@dataclass(frozen=True)
class CommandPipeline:
    """A runtime-controlled pipeline, preceded by an optional short-circuit operator."""

    operator: str
    commands: tuple[tuple[str, ...], ...]


@dataclass
class BashPolicy:
    path_policy: PathPolicy
    allow_write_commands: bool = True
    allow_python_inline: bool = False

    def validate(self, command: str, env: ToolEnvironment) -> tuple[CommandPipeline, ...]:
        for pattern in FORBIDDEN_PATTERNS:
            if re.search(pattern, command):
                raise PermissionError("bash command uses forbidden shell syntax")
        tokens = self._tokenize(command)
        pipelines = self._parse(tokens)
        for pipeline in pipelines:
            for segment in pipeline.commands:
                self._validate_segment(segment, env)
        return pipelines

    @staticmethod
    def _tokenize(command: str) -> list[str]:
        lexer = shlex.shlex(command, posix=True, punctuation_chars="|&;<>")
        lexer.whitespace_split = True
        tokens = list(lexer)
        if not tokens:
            raise ValueError("empty command")
        for token in tokens:
            if token == ";" or token == "&" or any(char in token for char in REDIRECTION_CHARS):
                raise PermissionError("redirections, background jobs, and command separators are not allowed")
        return tokens

    @staticmethod
    def _parse(tokens: list[str]) -> tuple[CommandPipeline, ...]:
        pipelines: list[CommandPipeline] = []
        commands: list[tuple[str, ...]] = []
        current: list[str] = []
        operator = ""

        def flush_command() -> None:
            nonlocal current
            if not current:
                raise ValueError("empty command segment")
            commands.append(tuple(current))
            current = []

        def flush_pipeline() -> None:
            nonlocal commands
            flush_command()
            pipelines.append(CommandPipeline(operator, tuple(commands)))
            commands = []

        for token in tokens:
            if token == PIPE:
                flush_command()
            elif token in CONTROL_OPERATORS:
                flush_pipeline()
                operator = token
            else:
                current.append(token)
        flush_pipeline()
        return tuple(pipelines)

    def _validate_segment(self, segment: tuple[str, ...], env: ToolEnvironment) -> None:
        raw_command = segment[0]
        if "/" in raw_command or "\\" in raw_command:
            raise PermissionError("executable paths are not allowed")
        command = Path(raw_command).name
        if command not in ALLOWLIST:
            raise PermissionError(f"command not allowed: {command}")
        if command in WRITE_COMMANDS and not self.allow_write_commands:
            raise PermissionError(f"write command not allowed in this phase: {command}")
        if command in {"python", "python3"} and "-c" in segment[1:] and not self.allow_python_inline:
            raise PermissionError("python -c is not allowed by this policy")
        if command == "git" and any(arg in {"--global", "--system"} for arg in segment[1:]):
            raise PermissionError("git global and system configuration are not allowed")
        for arg in segment[1:]:
            if self._looks_like_path(arg):
                self.path_policy.validate_access_path(arg, env)

    @staticmethod
    def _looks_like_path(arg: str) -> bool:
        if not arg or arg.startswith("-"):
            return False
        return (
            arg in {".", ".."}
            or "/" in arg
            or "\\" in arg
            or arg.startswith(".")
            or arg.endswith((".py", ".md", ".json", ".txt", ".toml", ".yaml", ".yml"))
        )
