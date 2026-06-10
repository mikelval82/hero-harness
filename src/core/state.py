from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol


class MissionStateProtocol(Protocol):
    phase: str
    task_id: str
    task_title: str
    task_num: int
    task_count: int
    completed: int
    mode: str
    gate: str
    waiting_approval: dict | None
    waiting_notified: bool


def update_state(
    phase: str,
    harness: Path,
    mission_state: MissionStateProtocol | None = None,
    task_id: str = "",
    task_title: str = "",
    task_num: int = 0,
    task_count: int = 0,
    completed: int = 0,
    mode: str = "",
    gate: str = "",
) -> None:
    if not gate:
        gate_file = harness / "_gate_mode"
        gate = gate_file.read_text(encoding="utf-8").strip() if gate_file.is_file() else "auto"

    state = {
        "phase": phase,
        "task_id": task_id,
        "task_title": task_title,
        "task_num": task_num,
        "task_count": task_count,
        "completed": completed,
        "mode": mode,
        "gate": gate,
    }
    (harness / "_state.json").write_text(json.dumps(state), encoding="utf-8")

    if mission_state is not None:
        mission_state.phase = phase
        mission_state.task_id = task_id
        mission_state.task_title = task_title
        mission_state.task_num = task_num
        mission_state.task_count = task_count
        mission_state.completed = completed
        mission_state.mode = mode
        mission_state.gate = gate


def _apply_gate_change(mode: str, harness: Path, mission_state: MissionStateProtocol | None) -> None:
    (harness / "_gate_mode").write_text(mode, encoding="utf-8")
    if mission_state is not None:
        mission_state.gate = mode
