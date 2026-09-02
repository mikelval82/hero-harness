from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum


class MissionStage(Enum):
    DRAFT = "draft"
    RESEARCHING = "researching"
    RESEARCH_REVIEW = "research_review"
    GRILLING = "grilling"
    DESIGN_REVIEW = "design_review"
    STRUCTURING = "structuring"
    WORKPLAN_REVIEW = "workplan_review"
    READY = "ready"
    TASK_PREPARATION = "task_preparation"
    TASK_REVIEW = "task_review"
    EXECUTING = "executing"
    RECONCILING = "reconciling"
    PAUSED = "paused"
    AMENDMENT_REVIEW = "amendment_review"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class SessionAction(Enum):
    SAVE_IDEA = "save_idea"
    RUN_RESEARCH = "run_research"
    START_GRILL = "start_grill"
    SKIP_GRILL = "skip_grill"
    REPLY = "reply"
    FINISH_GRILL = "finish_grill"
    APPROVE_DESIGN = "approve_design"
    RERUN_STRUCTURE = "rerun_structure"
    APPROVE_EXECUTION = "approve_execution"
    PREPARE_TASK = "prepare_task"
    REVISE_TASK_DOCUMENTS = "revise_task_documents"
    APPROVE_TASK = "approve_task"
    REQUEST_AMENDMENT = "request_amendment"
    PAUSE = "pause"
    RESUME = "resume"
    RETRY = "retry"
    ABORT = "abort"


_TRANSITIONS: dict[MissionStage, frozenset[MissionStage]] = {
    MissionStage.DRAFT: frozenset({MissionStage.RESEARCHING, MissionStage.BLOCKED}),
    MissionStage.RESEARCHING: frozenset({MissionStage.RESEARCH_REVIEW, MissionStage.BLOCKED}),
    MissionStage.RESEARCH_REVIEW: frozenset(
        {MissionStage.RESEARCHING, MissionStage.GRILLING, MissionStage.DESIGN_REVIEW, MissionStage.BLOCKED}
    ),
    MissionStage.GRILLING: frozenset({MissionStage.DESIGN_REVIEW, MissionStage.BLOCKED}),
    MissionStage.DESIGN_REVIEW: frozenset(
        {MissionStage.GRILLING, MissionStage.STRUCTURING, MissionStage.BLOCKED}
    ),
    MissionStage.STRUCTURING: frozenset({MissionStage.WORKPLAN_REVIEW, MissionStage.BLOCKED}),
    MissionStage.WORKPLAN_REVIEW: frozenset(
        {MissionStage.STRUCTURING, MissionStage.READY, MissionStage.BLOCKED}
    ),
    MissionStage.READY: frozenset(
        {MissionStage.TASK_PREPARATION, MissionStage.AMENDMENT_REVIEW, MissionStage.COMPLETED, MissionStage.BLOCKED}
    ),
    MissionStage.TASK_PREPARATION: frozenset({MissionStage.TASK_REVIEW, MissionStage.BLOCKED}),
    MissionStage.TASK_REVIEW: frozenset(
        {MissionStage.TASK_PREPARATION, MissionStage.EXECUTING, MissionStage.AMENDMENT_REVIEW, MissionStage.BLOCKED}
    ),
    MissionStage.EXECUTING: frozenset(
        {MissionStage.RECONCILING, MissionStage.PAUSED, MissionStage.BLOCKED}
    ),
    MissionStage.RECONCILING: frozenset(
        {MissionStage.READY, MissionStage.AMENDMENT_REVIEW, MissionStage.COMPLETED, MissionStage.BLOCKED}
    ),
    MissionStage.PAUSED: frozenset(
        {MissionStage.READY, MissionStage.AMENDMENT_REVIEW, MissionStage.BLOCKED}
    ),
    MissionStage.AMENDMENT_REVIEW: frozenset(
        {MissionStage.STRUCTURING, MissionStage.READY, MissionStage.BLOCKED}
    ),
    MissionStage.BLOCKED: frozenset({MissionStage.DRAFT, MissionStage.PAUSED, MissionStage.EXECUTING}),
    MissionStage.COMPLETED: frozenset(),
}


_ACTIONS: dict[MissionStage, tuple[SessionAction, ...]] = {
    MissionStage.DRAFT: (SessionAction.SAVE_IDEA, SessionAction.RUN_RESEARCH),
    MissionStage.RESEARCH_REVIEW: (
        SessionAction.RUN_RESEARCH,
        SessionAction.START_GRILL,
        SessionAction.SKIP_GRILL,
    ),
    MissionStage.GRILLING: (SessionAction.REPLY, SessionAction.FINISH_GRILL),
    MissionStage.DESIGN_REVIEW: (SessionAction.START_GRILL, SessionAction.APPROVE_DESIGN),
    MissionStage.WORKPLAN_REVIEW: (
        SessionAction.RERUN_STRUCTURE,
        SessionAction.APPROVE_EXECUTION,
    ),
    MissionStage.READY: (SessionAction.PREPARE_TASK, SessionAction.REQUEST_AMENDMENT),
    MissionStage.TASK_REVIEW: (
        SessionAction.REVISE_TASK_DOCUMENTS,
        SessionAction.APPROVE_TASK,
        SessionAction.REQUEST_AMENDMENT,
    ),
    MissionStage.EXECUTING: (SessionAction.PAUSE, SessionAction.ABORT),
    MissionStage.PAUSED: (SessionAction.RESUME, SessionAction.REQUEST_AMENDMENT, SessionAction.ABORT),
    MissionStage.AMENDMENT_REVIEW: (SessionAction.APPROVE_DESIGN,),
    MissionStage.BLOCKED: (SessionAction.RETRY, SessionAction.ABORT),
}


@dataclass(frozen=True)
class MissionSession:
    mission_id: str
    stage: MissionStage = MissionStage.DRAFT
    revision: int = 0
    active_phase: str = ""
    active_task_id: str = ""
    pending_interaction_id: str = ""
    approved_snapshot_id: str = ""
    blocked_reason: str = ""

    @property
    def allowed_actions(self) -> tuple[SessionAction, ...]:
        return _ACTIONS.get(self.stage, ())

    def move_to(
        self,
        stage: MissionStage,
        *,
        active_phase: str = "",
        active_task_id: str | None = None,
        pending_interaction_id: str = "",
        approved_snapshot_id: str | None = None,
        blocked_reason: str = "",
    ) -> MissionSession:
        if stage not in _TRANSITIONS[self.stage]:
            raise ValueError(f"Invalid mission transition: {self.stage.value} -> {stage.value}")
        return replace(
            self,
            stage=stage,
            revision=self.revision + 1,
            active_phase=active_phase,
            active_task_id=self.active_task_id if active_task_id is None else active_task_id,
            pending_interaction_id=pending_interaction_id,
            approved_snapshot_id=(
                self.approved_snapshot_id
                if approved_snapshot_id is None
                else approved_snapshot_id
            ),
            blocked_reason=blocked_reason,
        )

    def touch(self) -> MissionSession:
        return replace(self, revision=self.revision + 1)

    def to_json(self) -> dict[str, object]:
        return {
            "mission_id": self.mission_id,
            "stage": self.stage.value,
            "revision": self.revision,
            "active_phase": self.active_phase,
            "active_task_id": self.active_task_id,
            "pending_interaction_id": self.pending_interaction_id,
            "approved_snapshot_id": self.approved_snapshot_id,
            "blocked_reason": self.blocked_reason,
            "allowed_actions": [action.value for action in self.allowed_actions],
        }

    @classmethod
    def from_json(cls, data: dict[str, object]) -> MissionSession:
        return cls(
            mission_id=str(data["mission_id"]),
            stage=MissionStage(str(data.get("stage", MissionStage.DRAFT.value))),
            revision=int(data.get("revision", 0)),
            active_phase=str(data.get("active_phase", "")),
            active_task_id=str(data.get("active_task_id", "")),
            pending_interaction_id=str(data.get("pending_interaction_id", "")),
            approved_snapshot_id=str(data.get("approved_snapshot_id", "")),
            blocked_reason=str(data.get("blocked_reason", "")),
        )
