from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path

from mission_orchestrator.adapters.tools.file_tools import _schema
from mission_orchestrator.adapters.tools.process_environment import sanitized_child_environment
from mission_orchestrator.ports.tool_registry import ToolAccess, ToolEnvironment


@dataclass
class RunValidationTool:
    """Run the runtime-selected project validation, never provider-supplied code."""

    name: str = "RunValidation"
    timeout_seconds: int = 120
    access: ToolAccess = ToolAccess.TRUSTED_VALIDATION

    def schema(self) -> dict:
        return _schema(
            self.name,
            "Run the configured project validation selected by the runtime.",
            {"check_id": {"type": "string", "enum": ["target_validation"]}},
            ["check_id"],
        )

    def execute(self, input: dict, env: ToolEnvironment) -> str:
        if input.get("check_id") != "target_validation":
            raise ValueError("unknown validation check")
        script = self._validation_script(env.project_dir)
        if script is None:
            return "exit=not_configured\nNo mission validation script is configured."
        result = subprocess.run(
            self._argv(script),
            cwd=env.project_dir,
            text=True,
            capture_output=True,
            timeout=self.timeout_seconds,
            check=False,
            shell=False,
            env=sanitized_child_environment(),
        )
        output = (result.stdout or "") + (result.stderr or "")
        return f"exit={result.returncode}\n{output}".rstrip()

    @staticmethod
    def _validation_script(project_dir: Path) -> Path | None:
        if platform.system().lower().startswith("win"):
            names = ("mission-validate.cmd", "mission-validate.bat", "mission-validate.ps1", "mission-validate.sh")
        else:
            names = ("mission-validate.sh", "mission-validate.cmd", "mission-validate.bat", "mission-validate.ps1")
        for name in names:
            candidate = project_dir / name
            if candidate.is_file():
                return candidate
        return None

    @staticmethod
    def _argv(script: Path) -> list[str]:
        suffix = script.suffix.lower()
        if suffix == ".ps1":
            return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]
        if suffix in {".cmd", ".bat"}:
            return ["cmd.exe", "/c", str(script)]
        return [str(script)]
