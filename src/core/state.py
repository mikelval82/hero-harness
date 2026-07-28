from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any, Protocol


def _state_text(value: Any) -> str:
    return str(value.value) if isinstance(value, Enum) else str(value)


class ControlState(str, Enum):
    RUNNING = "running"
    PAUSE_PENDING = "pause_pending"
    PAUSED = "paused"
    ABORT_PENDING = "abort_pending"
    ABORTED = "aborted"
    COMPLETED = "completed"
    FAILED = "failed"


class InteractionKind(str, Enum):
    GRILL = "grill"
    APPROVAL = "approval"
    REVIEW_DECISION = "review_decision"


@dataclass(frozen=True)
class Interaction:
    id: str
    kind: InteractionKind
    task_id: str = ""
    prompt: str = ""
    accepted_update_id: int | str | None = None
    notified: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "task_id": self.task_id,
            "prompt": self.prompt,
            "accepted_update_id": self.accepted_update_id,
            "notified": self.notified,
        }


class MissionState:
    """Thread-safe in-memory state shared by the runner and control adapters."""

    def __init__(
        self,
        *,
        phase: str = "",
        task_id: str = "",
        task_title: str = "",
        task_num: int = 0,
        task_count: int = 0,
        completed: int = 0,
        mode: str = "full",
        gate: str = "auto",
        last_activity: str = "",
        control_state: ControlState | str = ControlState.RUNNING,
        interaction: Interaction | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._phase = _state_text(phase)
        self._task_id = task_id
        self._task_title = task_title
        self._task_num = task_num
        self._task_count = task_count
        self._completed = completed
        self._mode = mode
        self._gate = gate
        self._last_activity = last_activity
        self._control_state = ControlState(control_state)
        self._interaction = interaction

    def update_progress(
        self,
        *,
        phase: str,
        task_id: str = "",
        task_title: str = "",
        task_num: int = 0,
        task_count: int = 0,
        completed: int = 0,
        mode: str = "",
        gate: str = "",
    ) -> None:
        with self._lock:
            self._phase = _state_text(phase)
            self._task_id = task_id
            self._task_title = task_title
            self._task_num = task_num
            self._task_count = task_count
            self._completed = completed
            if mode:
                self._mode = mode
            if gate:
                self._gate = gate

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "phase": self._phase,
                "task_id": self._task_id,
                "task_title": self._task_title,
                "task_num": self._task_num,
                "task_count": self._task_count,
                "completed": self._completed,
                "mode": self._mode,
                "gate": self._gate,
                "last_activity": self._last_activity,
                "control_state": self._control_state.value,
                "interaction": self._interaction.as_dict() if self._interaction else None,
            }

    def set_control_state(self, state: ControlState | str) -> ControlState:
        value = ControlState(state)
        with self._lock:
            self._control_state = value
        return value

    def request_pause(self) -> bool:
        with self._lock:
            if self._control_state != ControlState.RUNNING or self._interaction is not None:
                return False
            self._control_state = ControlState.PAUSE_PENDING
            return True

    def request_resume(self) -> bool:
        with self._lock:
            if self._control_state not in {ControlState.PAUSE_PENDING, ControlState.PAUSED}:
                return False
            self._control_state = ControlState.RUNNING
            return True

    def request_abort(self) -> bool:
        with self._lock:
            if self._control_state in {
                ControlState.ABORT_PENDING,
                ControlState.ABORTED,
                ControlState.COMPLETED,
                ControlState.FAILED,
            }:
                return False
            self._control_state = ControlState.ABORT_PENDING
            return True

    def open_interaction(
        self,
        kind: InteractionKind | str,
        *,
        task_id: str = "",
        prompt: str = "",
    ) -> Interaction:
        interaction = Interaction(
            id=uuid.uuid4().hex,
            kind=InteractionKind(kind),
            task_id=task_id,
            prompt=prompt,
        )
        with self._lock:
            if self._interaction is not None:
                raise RuntimeError(
                    f"interaction {self._interaction.id} is still active"
                )
            self._interaction = interaction
        return interaction

    def get_interaction(self) -> Interaction | None:
        with self._lock:
            return replace(self._interaction) if self._interaction else None

    def reserve_interaction(
        self,
        interaction_id: str,
        update_id: int | str,
    ) -> str:
        """Reserve the current interaction once.

        Returns ``accepted``, ``already_accepted`` or ``stale``.
        """
        with self._lock:
            current = self._interaction
            if current is None or current.id != interaction_id:
                return "stale"
            if current.accepted_update_id is not None:
                return "already_accepted"
            self._interaction = replace(current, accepted_update_id=update_id)
            return "accepted"

    def interaction_accepts(
        self,
        interaction_id: str | None,
        update_id: int | str | None,
    ) -> bool:
        with self._lock:
            current = self._interaction
            return bool(
                current
                and interaction_id == current.id
                and update_id is not None
                and update_id == current.accepted_update_id
            )

    def mark_interaction_notified(self, interaction_id: str) -> bool:
        with self._lock:
            current = self._interaction
            if current is None or current.id != interaction_id:
                return False
            self._interaction = replace(current, notified=True)
            return True

    def close_interaction(self, interaction_id: str) -> bool:
        with self._lock:
            if self._interaction is None or self._interaction.id != interaction_id:
                return False
            self._interaction = None
            return True

    # Locked properties keep status readers compatible while avoiding exposed
    # mutable dataclass state.
    def _get(self, name: str):
        with self._lock:
            return getattr(self, f"_{name}")

    def _set(self, name: str, value) -> None:
        with self._lock:
            setattr(self, f"_{name}", value)

    phase = property(lambda self: self._get("phase"), lambda self, value: self._set("phase", _state_text(value)))
    task_id = property(lambda self: self._get("task_id"), lambda self, value: self._set("task_id", value))
    task_title = property(lambda self: self._get("task_title"), lambda self, value: self._set("task_title", value))
    task_num = property(lambda self: self._get("task_num"), lambda self, value: self._set("task_num", value))
    task_count = property(lambda self: self._get("task_count"), lambda self, value: self._set("task_count", value))
    completed = property(lambda self: self._get("completed"), lambda self, value: self._set("completed", value))
    mode = property(lambda self: self._get("mode"), lambda self, value: self._set("mode", value))
    gate = property(lambda self: self._get("gate"), lambda self, value: self._set("gate", value))
    last_activity = property(lambda self: self._get("last_activity"), lambda self, value: self._set("last_activity", value))

    @property
    def control_state(self) -> ControlState:
        return self._get("control_state")

    @control_state.setter
    def control_state(self, value: ControlState | str) -> None:
        self._set("control_state", ControlState(value))

    @property
    def interaction(self) -> Interaction | None:
        return self.get_interaction()


class MissionStateProtocol(Protocol):
    phase: str
    task_id: str
    task_title: str
    task_num: int
    task_count: int
    completed: int
    mode: str
    gate: str
    last_activity: str
    control_state: ControlState

    def update_progress(self, **values) -> None: ...
    def snapshot(self) -> dict[str, Any]: ...
    def set_control_state(self, state: ControlState | str) -> ControlState: ...
    def request_pause(self) -> bool: ...
    def request_resume(self) -> bool: ...
    def request_abort(self) -> bool: ...
    def open_interaction(self, kind: InteractionKind | str, *, task_id: str = "", prompt: str = "") -> Interaction: ...
    def get_interaction(self) -> Interaction | None: ...
    def reserve_interaction(self, interaction_id: str, update_id: int | str) -> str: ...
    def interaction_accepts(self, interaction_id: str | None, update_id: int | str | None) -> bool: ...
    def mark_interaction_notified(self, interaction_id: str) -> bool: ...
    def close_interaction(self, interaction_id: str) -> bool: ...


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(path)


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
        "phase": _state_text(phase),
        "task_id": task_id,
        "task_title": task_title,
        "task_num": task_num,
        "task_count": task_count,
        "completed": completed,
        "mode": mode,
        "gate": gate,
    }
    _atomic_write_json(harness / "_state.json", state)

    if mission_state is not None:
        mission_state.update_progress(
            phase=_state_text(phase),
            task_id=task_id,
            task_title=task_title,
            task_num=task_num,
            task_count=task_count,
            completed=completed,
            mode=mode,
            gate=gate,
        )


def _apply_gate_change(mode: str, harness: Path, mission_state: MissionStateProtocol | None) -> None:
    if mode not in {"auto", "manual"}:
        raise ValueError(f"invalid gate mode: {mode}")
    (harness / "_gate_mode").write_text(mode, encoding="utf-8")
    if mission_state is not None:
        mission_state.gate = mode
