from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
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

    # The provider can only name a check from this runtime-owned registry.
    TRUSTED_CHECKS = {"target_validation"}

    def schema(self) -> dict:
        return _schema(
            self.name,
            "Run the configured project validation selected by the runtime.",
            {"check_id": {"type": "string", "enum": ["target_validation"]}},
            ["check_id"],
        )

    def execute(self, input: dict, env: ToolEnvironment) -> str:
        check_id = input.get("check_id")
        if check_id not in self.TRUSTED_CHECKS:
            raise ValueError("unknown validation check")
        script = self._validation_script(env.project_dir)
        if script is None:
            self._write_receipt(env.harness_dir, check_id, "not_run", "No mission validation script is configured.", "")
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
        status = "pass" if result.returncode == 0 else "fail"
        self._write_receipt(env.harness_dir, check_id, status, f"exit={result.returncode}", output, script)
        return f"exit={result.returncode}\n{output}".rstrip()

    @staticmethod
    def _write_receipt(
        harness_dir: Path, check_id: str, status: str, detail: str, output: str, script: Path | None = None
    ) -> None:
        directory = harness_dir / "validation-evidence"
        directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "check_id": check_id,
            "status": status,
            "actor": "RunValidation",
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "document_ref": str(script) if script else "",
            "detail": detail,
            "output_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
            "output_bytes": len(output.encode("utf-8")),
        }
        target = directory / f"{check_id}.json"
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()

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
