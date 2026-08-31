from __future__ import annotations

import fnmatch
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from mission_orchestrator.adapters.tools.file_tools import _schema
from mission_orchestrator.adapters.tools.path_policy import PathPolicy
from mission_orchestrator.ports.tool_registry import ToolAccess, ToolEnvironment


def _git_visible_files(root: Path) -> list[Path] | None:
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=root,
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return [root / line for line in result.stdout.splitlines() if line.strip()]


@dataclass
class GlobTool:
    policy: PathPolicy
    name: str = "Glob"
    access: ToolAccess = ToolAccess.READ_ONLY

    def schema(self) -> dict:
        return _schema(
            self.name,
            "Find files matching a glob pattern.",
            {"pattern": {"type": "string"}, "path": {"type": "string"}},
            ["pattern"],
        )

    def execute(self, input: dict, env: ToolEnvironment) -> str:
        base = self.policy.validate_access_path(str(input.get("path") or "."), env)
        pattern = str(input["pattern"])
        files = _git_visible_files(base) if (base / ".git").exists() else None
        if files is None:
            files = [path for path in base.glob(pattern) if path.is_file()]
        else:
            files = [path for path in files if fnmatch.fnmatch(path.relative_to(base).as_posix(), pattern)]
        files.sort(key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True)
        return "\n".join(str(path.relative_to(base)) if path.is_relative_to(base) else str(path) for path in files)


@dataclass
class GrepTool:
    policy: PathPolicy
    name: str = "Grep"
    access: ToolAccess = ToolAccess.READ_ONLY

    def schema(self) -> dict:
        return _schema(
            self.name,
            "Search visible files for a regex pattern.",
            {
                "pattern": {"type": "string"},
                "path": {"type": "string"},
                "glob": {"type": "string"},
                "output_mode": {
                    "type": "string",
                    "enum": ["files_with_matches", "content", "count"],
                },
                "context": {"type": "integer"},
                "head_limit": {"type": "integer"},
            },
            ["pattern"],
        )

    def execute(self, input: dict, env: ToolEnvironment) -> str:
        root = self.policy.validate_access_path(str(input.get("path") or "."), env)
        pattern = str(input["pattern"])
        glob = input.get("glob")
        mode = str(input.get("output_mode") or "content")
        head_limit = int(input.get("head_limit", 50) or 50)
        rg = shutil.which("rg")
        if rg:
            return self._run_rg(rg, root, pattern, glob, mode, head_limit)
        return self._fallback(root, pattern, glob, mode, head_limit)

    def _run_rg(
        self,
        rg: str,
        root: Path,
        pattern: str,
        glob: object,
        mode: str,
        head_limit: int,
    ) -> str:
        args = [rg, "--line-number"]
        if mode == "files_with_matches":
            args.append("--files-with-matches")
        elif mode == "count":
            args.append("--count")
        if glob:
            args.extend(["--glob", str(glob)])
        args.append(pattern)
        try:
            result = subprocess.run(
                args,
                cwd=root,
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
        except Exception as exc:
            return f"grep failed: {exc}"
        lines = result.stdout.splitlines()[:head_limit]
        return "\n".join(lines)

    def _fallback(
        self,
        root: Path,
        pattern: str,
        glob: object,
        mode: str,
        head_limit: int,
    ) -> str:
        regex = re.compile(pattern)
        files = _git_visible_files(root) or [path for path in root.rglob("*") if path.is_file()]
        if glob:
            files = [path for path in files if fnmatch.fnmatch(path.relative_to(root).as_posix(), str(glob))]
        output: list[str] = []
        for path in files:
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception:
                continue
            matches = [(i, line) for i, line in enumerate(lines, start=1) if regex.search(line)]
            if not matches:
                continue
            rel = path.relative_to(root).as_posix()
            if mode == "files_with_matches":
                output.append(rel)
            elif mode == "count":
                output.append(f"{rel}:{len(matches)}")
            else:
                output.extend(f"{rel}:{line_no}:{line}" for line_no, line in matches)
            if len(output) >= head_limit:
                break
        return "\n".join(output[:head_limit])
