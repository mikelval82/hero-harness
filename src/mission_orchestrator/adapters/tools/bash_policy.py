from __future__ import annotations

import re
import shlex
from dataclasses import dataclass

from mission_orchestrator.adapters.tools.path_policy import PathPolicy
from mission_orchestrator.ports.tool_registry import ToolEnvironment


FORBIDDEN_PATTERNS = (
    r"`",
    r"\$\(",
    r"<\(",
    r">\(",
    r"<<",
    r">>",
)
SEPARATORS = {"|", "&&", "||", ";"}
REDIRECTS = {">", "<", "2>", "1>", "&>", "2>&1"}
ALLOWLIST = {
    "python3",
    "python",
    "git",
    "wc",
    "sort",
    "grep",
    "awk",
    "sed",
    "jq",
    "file",
    "diff",
    "tr",
    "cut",
    "uniq",
    "tee",
    "find",
    "mkdir",
    "cp",
    "mv",
    "rm",
    "touch",
    "chmod",
    "printf",
    "test",
    "read",
    "cd",
    "export",
    "echo",
    "true",
    "false",
    "cat",
    "head",
    "tail",
    "ls",
}
WRITE_COMMANDS = {"mkdir", "cp", "mv", "rm", "touch", "chmod", "tee"}


@dataclass
class BashPolicy:
    path_policy: PathPolicy
    allow_write_commands: bool = True
    allow_python_inline: bool = False

    def validate(self, command: str, env: ToolEnvironment) -> list[list[str]]:
        for pattern in FORBIDDEN_PATTERNS:
            if re.search(pattern, command):
                raise PermissionError("bash command uses forbidden shell syntax")
        tokens = shlex.split(command, posix=True)
        if not tokens:
            raise ValueError("empty command")
        if any(token in REDIRECTS or token.endswith(">") for token in tokens):
            raise PermissionError("redirections are not allowed")
        if "&" in tokens:
            raise PermissionError("background jobs are not allowed")
        segments: list[list[str]] = []
        current: list[str] = []
        for token in tokens:
            if token in SEPARATORS:
                if not current:
                    raise ValueError("empty command segment")
                segments.append(current)
                current = []
            else:
                current.append(token)
        if current:
            segments.append(current)
        for segment in segments:
            self._validate_segment(segment, env)
        return segments

    def _validate_segment(self, segment: list[str], env: ToolEnvironment) -> None:
        command = segment[0]
        if command not in ALLOWLIST:
            raise PermissionError(f"command not allowed: {command}")
        if command in WRITE_COMMANDS and not self.allow_write_commands:
            raise PermissionError(f"write command not allowed in this phase: {command}")
        if command in {"python", "python3"} and any(arg == "-c" for arg in segment[1:]):
            if not self.allow_python_inline:
                raise PermissionError("python -c is not allowed by this policy")
        for arg in segment[1:]:
            if self._looks_like_path(arg):
                self.path_policy.validate_access_path(arg, env)

    @staticmethod
    def _looks_like_path(arg: str) -> bool:
        if arg.startswith("-"):
            return False
        return (
            "/" in arg
            or "\\" in arg
            or arg.startswith(".")
            or arg.endswith((".py", ".md", ".json", ".txt", ".toml", ".yaml", ".yml"))
        )

