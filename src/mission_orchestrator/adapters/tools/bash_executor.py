from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from mission_orchestrator.adapters.tools.bash_policy import BashPolicy, CommandPipeline
from mission_orchestrator.adapters.tools.file_tools import _schema
from mission_orchestrator.adapters.tools.process_environment import sanitized_child_environment
from mission_orchestrator.ports.tool_registry import ToolAccess, ToolEnvironment


@dataclass(frozen=True)
class _CommandResult:
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0
    cwd: Path | None = None


@dataclass
class BashTool:
    policy: BashPolicy
    name: str = "Bash"
    timeout_seconds: int = 120
    access: ToolAccess = ToolAccess.PROJECT_EXECUTION

    def schema(self) -> dict:
        return _schema(
            self.name,
            "Run an allowlisted argv command pipeline inside the project directory.",
            {"command": {"type": "string"}},
            ["command"],
        )

    def execute(self, input: dict, env: ToolEnvironment) -> str:
        pipelines = self.policy.validate(str(input["command"]), env)
        cwd = env.project_dir.resolve()
        output: list[str] = []
        last_code = 0
        try:
            for pipeline in pipelines:
                if pipeline.operator == "&&" and last_code != 0:
                    continue
                if pipeline.operator == "||" and last_code == 0:
                    continue
                result = self._run_pipeline(pipeline, cwd, env)
                output.extend((result.stdout, result.stderr))
                last_code = result.returncode
                if result.cwd is not None:
                    cwd = result.cwd
        except subprocess.TimeoutExpired:
            return f"exit=timeout\ncommand timed out after {self.timeout_seconds}s"
        return f"exit={last_code}\n{''.join(output)}".rstrip()

    def _run_pipeline(self, pipeline: CommandPipeline, cwd: Path, env: ToolEnvironment) -> _CommandResult:
        stdin_text = ""
        stderr: list[str] = []
        current_cwd = cwd
        result = _CommandResult(cwd=cwd)
        for argv in pipeline.commands:
            result = self._run_command(argv, stdin_text, current_cwd, env)
            stdin_text = result.stdout
            if result.stderr:
                stderr.append(result.stderr)
            if result.cwd is not None:
                current_cwd = result.cwd
            if result.returncode != 0:
                break
        return _CommandResult(stdin_text, "".join(stderr), result.returncode, current_cwd)

    def _run_command(self, argv: tuple[str, ...], stdin_text: str, cwd: Path, env: ToolEnvironment) -> _CommandResult:
        command = argv[0]
        args = argv[1:]
        if command == "cd":
            target = args[0] if args else "."
            path = self._resolve_path(target, cwd, env)
            if not path.is_dir():
                return _CommandResult(stderr=f"cd: no such directory: {target}\n", returncode=1, cwd=cwd)
            return _CommandResult(cwd=path)
        if command == "export":
            return _CommandResult(stdout="export ignored: environment is not persisted\n", cwd=cwd)
        if command == "echo":
            return _CommandResult(stdout=" ".join(args) + "\n", cwd=cwd)
        if command == "true":
            return _CommandResult(cwd=cwd)
        if command == "false":
            return _CommandResult(returncode=1, cwd=cwd)
        if command == "cat":
            return self._cat(args, stdin_text, cwd, env)
        if command in {"head", "tail"}:
            return self._head_tail(command, args, stdin_text, cwd, env)
        if command == "ls":
            return self._ls(args, cwd, env)
        try:
            completed = subprocess.run(
                list(argv), input=stdin_text, cwd=cwd, text=True, capture_output=True,
                timeout=self.timeout_seconds, check=False, shell=False, env=sanitized_child_environment(),
            )
        except FileNotFoundError:
            return _CommandResult(stderr=f"command not found: {command}\n", returncode=127, cwd=cwd)
        return _CommandResult(completed.stdout, completed.stderr, completed.returncode, cwd)

    def _resolve_path(self, raw_path: str, cwd: Path, env: ToolEnvironment) -> Path:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = cwd / candidate
        return self.policy.path_policy.validate_access_path(str(candidate), env)

    def _cat(self, args: tuple[str, ...], stdin_text: str, cwd: Path, env: ToolEnvironment) -> _CommandResult:
        paths = [arg for arg in args if not arg.startswith("-")]
        if not paths:
            return _CommandResult(stdout=stdin_text, cwd=cwd)
        output: list[str] = []
        for raw_path in paths:
            path = self._resolve_path(raw_path, cwd, env)
            if not path.is_file():
                return _CommandResult(stderr=f"cat: {raw_path}: No such file\n", returncode=1, cwd=cwd)
            output.append(path.read_text(encoding="utf-8", errors="replace"))
        return _CommandResult(stdout="".join(output), cwd=cwd)

    def _head_tail(self, command: str, args: tuple[str, ...], stdin_text: str, cwd: Path, env: ToolEnvironment) -> _CommandResult:
        count = 10
        paths: list[str] = []
        index = 0
        while index < len(args):
            if args[index] == "-n" and index + 1 < len(args):
                count = int(args[index + 1])
                index += 2
            elif args[index].startswith("-n") and len(args[index]) > 2:
                count = int(args[index][2:])
                index += 1
            else:
                paths.append(args[index])
                index += 1
        source = stdin_text
        if paths:
            read = self._cat(tuple(paths), "", cwd, env)
            if read.returncode != 0:
                return read
            source = read.stdout
        lines = source.splitlines()
        chosen = lines[:count] if command == "head" else lines[-count:]
        return _CommandResult(stdout="\n".join(chosen) + ("\n" if chosen else ""), cwd=cwd)

    def _ls(self, args: tuple[str, ...], cwd: Path, env: ToolEnvironment) -> _CommandResult:
        raw_path = next((arg for arg in reversed(args) if not arg.startswith("-")), ".")
        path = self._resolve_path(raw_path, cwd, env)
        if path.is_file():
            return _CommandResult(stdout=path.name + "\n", cwd=cwd)
        if not path.exists():
            return _CommandResult(stderr=f"ls: cannot access '{raw_path}'\n", returncode=1, cwd=cwd)
        return _CommandResult(stdout="\n".join(sorted(child.name for child in path.iterdir())) + "\n", cwd=cwd)
