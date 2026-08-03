from __future__ import annotations

import json
from datetime import datetime

from mission_orchestrator.ports.artifacts import ArtifactStore


class FilesystemMissionLogger:
    def __init__(self, artifacts: ArtifactStore) -> None:
        self.artifacts = artifacts

    def log(self, message: str) -> None:
        line = f"[{datetime.now().isoformat(timespec='seconds')}] {message}"
        print(line)
        try:
            self.artifacts.append_text("mission.log", line + "\n")
        except Exception:
            pass

    def tool_call(self, name: str, input: dict) -> None:
        descriptions = {
            "Read": f"Reading {input.get('file_path', '')}",
            "Write": f"Writing {input.get('file_path', '')}",
            "Edit": f"Editing {input.get('file_path', '')}",
            "Bash": f"Running: {str(input.get('command', ''))[:60]}",
            "Grep": f"Searching '{input.get('pattern', '')}'",
            "Glob": f"Finding files {input.get('pattern', '')}",
        }
        self.log(descriptions.get(name, f"Tool {name}"))
        try:
            self.artifacts.append_text("_progress.txt", descriptions.get(name, name) + "\n")
        except Exception:
            pass

    def metric(self, record: dict) -> None:
        try:
            self.artifacts.append_text("_metrics.jsonl", json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass

