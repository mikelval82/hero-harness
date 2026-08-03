from __future__ import annotations

import json

from mission_orchestrator.domain.mission import GateMode, MissionSnapshot, WaitingApproval
from mission_orchestrator.ports.artifacts import ArtifactStore


class FilesystemMissionStateStore:
    def __init__(self, artifacts: ArtifactStore, initial_gate: GateMode = GateMode.AUTO) -> None:
        self.artifacts = artifacts
        if not self.artifacts.exists("_gate_mode"):
            self.set_gate_mode(initial_gate)

    def update_phase(self, snapshot: MissionSnapshot) -> None:
        self.artifacts.write_text("_state.json", json.dumps(snapshot.to_json(), indent=2) + "\n")

    def set_gate_mode(self, mode: GateMode) -> None:
        self.artifacts.write_text("_gate_mode", mode.value)

    def get_gate_mode(self) -> GateMode:
        raw = self.artifacts.read_text("_gate_mode", default=GateMode.AUTO.value).strip()
        return GateMode.MANUAL if raw in {"manual", "on", "true", "1"} else GateMode.AUTO

    def set_waiting_approval(self, info: WaitingApproval | None) -> None:
        if info is None:
            self.artifacts.delete("_waiting_approval")
            return
        self.artifacts.write_text("_waiting_approval", json.dumps(info.to_json(), indent=2) + "\n")

    def mark_waiting_notified(self, notified: bool) -> None:
        raw = self.artifacts.read_text("_waiting_approval", default="")
        if not raw:
            return
        info = WaitingApproval.from_json(json.loads(raw))
        self.set_waiting_approval(
            WaitingApproval(info.task_id, info.task_title, info.verdict, notified=notified)
        )

    def load_snapshot(self) -> MissionSnapshot | None:
        raw = self.artifacts.read_text("_state.json", default="")
        if not raw:
            return None
        return MissionSnapshot.from_json(json.loads(raw))

