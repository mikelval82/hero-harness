from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


class MissionRegistry:
    def __init__(self, registry_path: Path | None = None) -> None:
        self.registry_path = registry_path or (Path.home() / ".harness" / "_missions.json")

    def register(self, tag: str, harness_path: Path, pid: int | None = None) -> None:
        data = self._load()
        data[tag] = {
            "harness_path": str(harness_path),
            "pid": pid or os.getpid(),
            "started": datetime.now(timezone.utc).isoformat(),
        }
        self._save(data)

    def active(self) -> dict[str, dict]:
        data = self._load()
        cleaned = {
            tag: info
            for tag, info in data.items()
            if self._pid_alive(int(info.get("pid", 0) or 0))
        }
        if cleaned != data:
            self._save(cleaned)
        return cleaned

    def _load(self) -> dict[str, dict]:
        if not self.registry_path.exists():
            return {}
        try:
            data = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self, data: dict[str, dict]) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.registry_path.with_name(f".{self.registry_path.name}.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, self.registry_path)

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

