from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from mission_orchestrator.adapters.tools.bash_policy import BashPolicy
from mission_orchestrator.adapters.tools.file_tools import _schema
from mission_orchestrator.ports.tool_registry import ToolEnvironment


@dataclass
class BashTool:
    policy: BashPolicy
    name: str = "Bash"
    timeout_seconds: int = 120

    def schema(self) -> dict:
        return _schema(
            self.name,
            "Run an allowlisted shell command inside the project directory.",
            {"command": {"type": "string"}},
            ["command"],
        )

    def execute(self, input: dict, env: ToolEnvironment) -> str:
        command = str(input["command"])
        segments = self.policy.validate(command, env)
        if len(segments) == 1:
            builtin = self._run_builtin(segments[0], env)
            if builtin is not None:
                return builtin
            result = subprocess.run(
                segments[0],
                cwd=env.project_dir,
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        else:
            result = subprocess.run(
                command,
                cwd=env.project_dir,
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                shell=True,
                check=False,
            )
        output = (result.stdout or "") + (result.stderr or "")
        return f"exit={result.returncode}\n{output}".rstrip()

    def _run_builtin(self, segment: list[str], env: ToolEnvironment) -> str | None:
        command = segment[0]
        args = segment[1:]
        if command == "true":
            return "exit=0"
        if command == "false":
            return "exit=1"
        if command == "echo":
            return " ".join(args)
        if command == "cd":
            target = args[0] if args else str(env.project_dir)
            path = self.policy.path_policy.validate_access_path(target, env)
            return str(path)
        if command == "export":
            return "export ignored: environment is not persisted"
        if command == "cat":
            return "\n".join(self._read_file(arg, env) for arg in args)
        if command in {"head", "tail"}:
            return self._head_tail(command, args, env)
        if command == "ls":
            target = args[-1] if args else "."
            path = self.policy.path_policy.validate_access_path(target, env)
            if path.is_file():
                return path.name
            return "\n".join(sorted(child.name for child in path.iterdir()))
        return None

    def _read_file(self, raw_path: str, env: ToolEnvironment) -> str:
        path = self.policy.path_policy.validate_access_path(raw_path, env)
        return path.read_text(encoding="utf-8", errors="replace")

    def _head_tail(self, command: str, args: list[str], env: ToolEnvironment) -> str:
        count = 10
        paths: list[str] = []
        index = 0
        while index < len(args):
            if args[index] == "-n" and index + 1 < len(args):
                count = int(args[index + 1])
                index += 2
            else:
                paths.append(args[index])
                index += 1
        if not paths:
            return ""
        lines = self._read_file(paths[0], env).splitlines()
        selected = lines[:count] if command == "head" else lines[-count:]
        return "\n".join(selected)

