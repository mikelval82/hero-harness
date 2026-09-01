from __future__ import annotations

from pathlib import Path

from mission_orchestrator.ports.tool_registry import ToolEnvironment


def _is_inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


class PathPolicy:
    def resolve(self, raw_path: str, env: ToolEnvironment) -> Path:
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = env.project_dir / path
        return path.resolve()

    def validate_access_path(self, raw_path: str, env: ToolEnvironment) -> Path:
        path = self.resolve(raw_path, env)
        project = env.project_dir.resolve()
        harness = env.harness_dir.resolve()
        if _is_inside(path, project) or _is_inside(path, harness) or path == project or path == harness:
            return path
        raise PermissionError(f"path escapes project/harness: {raw_path}")

    def validate_write_path(self, raw_path: str, env: ToolEnvironment) -> Path:
        return self.validate_access_path(raw_path, env)

