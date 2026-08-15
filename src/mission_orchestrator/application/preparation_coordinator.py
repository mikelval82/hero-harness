from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone

from mission_orchestrator.adapters.design.store import DesignStore
from mission_orchestrator.application.design_approval import DesignApprovalService
from mission_orchestrator.application.document_service import MissionDocumentService
from mission_orchestrator.application.phase_executor import PhaseExecutor
from mission_orchestrator.application.services import AppServices
from mission_orchestrator.domain.design import ApplyStatus
from mission_orchestrator.domain.document import DocumentSaveStatus
from mission_orchestrator.domain.mission import MissionContext
from mission_orchestrator.domain.phase import PhaseName
from mission_orchestrator.domain.session import MissionSession, MissionStage
from mission_orchestrator.domain.workplan import validate_plan
from mission_orchestrator.ports.documents import DocumentCatalog
from mission_orchestrator.ports.session_store import MissionSessionStore, SessionConflictError


class InvalidSessionAction(RuntimeError):
    def __init__(self, stage: MissionStage, action: str) -> None:
        super().__init__(f"action {action!r} is not allowed while mission is {stage.value}")
        self.stage = stage
        self.action = action


@dataclass(frozen=True)
class PreparationResult:
    session: MissionSession
    accepted: bool = True
    detail: str = ""


class PreparationCoordinator:
    def __init__(
        self,
        *,
        services: AppServices,
        context: MissionContext,
        sessions: MissionSessionStore,
        documents: MissionDocumentService,
        catalog: DocumentCatalog,
    ) -> None:
        self.services = services
        self.context = context
        self.sessions = sessions
        self.documents = documents
        self.catalog = catalog
        self.phases = PhaseExecutor(services, context)
        self._action_lock = threading.Lock()

    def session(self) -> MissionSession:
        return self.sessions.load(self.context.mission_tag)

    def save_idea(
        self,
        *,
        content: str,
        expected_session_revision: int,
        base_document_revision: int,
        command_id: str,
    ) -> PreparationResult:
        if not content.strip():
            raise ValueError("idea Markdown must not be empty")
        with self._action_lock:
            current = self._expected(expected_session_revision, MissionStage.DRAFT, "save_idea")
            document = self.documents.save(
                logical_id="mission/idea",
                alias="idea.md",
                content=content,
                author="HUMAN",
                base_revision=base_document_revision,
                command_id=command_id,
            )
            if document.status is not DocumentSaveStatus.APPLIED:
                return PreparationResult(current, False, document.detail)
            updated = current.touch()
            self._save(current, updated)
            return PreparationResult(updated)

    def save_brief_seed(
        self,
        *,
        content: str,
        expected_session_revision: int,
        base_document_revision: int,
        command_id: str,
    ) -> PreparationResult:
        if not content.strip():
            raise ValueError("brief seed Markdown must not be empty")
        with self._action_lock:
            current = self._expected(
                expected_session_revision,
                MissionStage.DRAFT,
                "save_brief_seed",
            )
            document = self.documents.save(
                logical_id="mission/brief-seed",
                alias="brief-seed.md",
                content=content,
                author="HUMAN",
                base_revision=base_document_revision,
                command_id=command_id,
            )
            if document.status is not DocumentSaveStatus.APPLIED:
                return PreparationResult(current, False, document.detail)
            updated = current.touch()
            self._save(current, updated)
            return PreparationResult(updated)

    def run_research(self, *, expected_session_revision: int) -> PreparationResult:
        with self._action_lock:
            current = self._expected(
                expected_session_revision,
                (MissionStage.DRAFT, MissionStage.RESEARCH_REVIEW),
                "run_research",
            )
            if (
                self.catalog.get("mission/idea") is None
                and self.catalog.get("mission/brief-seed") is None
            ):
                raise ValueError("mission idea or brief seed must be saved before research")
            running = current.move_to(MissionStage.RESEARCHING, active_phase="research")
            self._save(current, running)
            self.services.code_graph.build(self.context.project_dir)
            execution = self.phases.run(PhaseName.RESEARCH)
            self.documents.capture_mission_document(
                "mission/brainstorm",
                author="AGENT",
                phase="research",
            )
            if execution.block is not None:
                return self._block(running, str(execution.block))
            review = running.move_to(MissionStage.RESEARCH_REVIEW)
            self._save(running, review)
            return PreparationResult(review)

    def run_grill(self, *, expected_session_revision: int) -> PreparationResult:
        with self._action_lock:
            current = self._expected(
                expected_session_revision,
                (MissionStage.RESEARCH_REVIEW, MissionStage.DESIGN_REVIEW),
                "start_grill",
            )
            running = current.move_to(MissionStage.GRILLING, active_phase="grill")
            self._save(current, running)
            execution = self.phases.run(PhaseName.GRILL)
            self.documents.capture_mission_document(
                "mission/brief",
                author="AGENT",
                phase="grill",
            )
            if execution.block is not None:
                return self._block(running, str(execution.block))
            review = running.move_to(MissionStage.DESIGN_REVIEW)
            self._save(running, review)
            return PreparationResult(review)

    def approve_design_and_structure(
        self,
        *,
        expected_session_revision: int,
        base_design_revision: int,
        base_brief_revision: int | None = None,
    ) -> PreparationResult:
        with self._action_lock:
            current = self._expected(
                expected_session_revision,
                (MissionStage.DESIGN_REVIEW, MissionStage.AMENDMENT_REVIEW),
                "approve_design",
            )
            design = DesignApprovalService(
                harness_dir=self.context.harness_dir,
                project_scope_dir=self.context.project_scope_dir,
                artifacts=self.services.artifacts,
                events=self.services.events,
                catalog=self.catalog,
                git=self.services.git,
                project_name=self.context.project_name,
                project_dir=self.context.project_dir,
            ).approve(
                base_revision=base_design_revision,
                base_brief_revision=base_brief_revision,
            )
            if design.status is not ApplyStatus.APPLIED:
                return PreparationResult(
                    current,
                    False,
                    design.detail
                    or f"design revision conflict; current revision is {design.design_revision}",
                )
            running = current.move_to(
                MissionStage.STRUCTURING,
                active_phase="structure",
                approved_snapshot_id=design.snapshot_id,
            )
            self._save(current, running)
            execution = self.phases.run(PhaseName.STRUCTURE)
            self.documents.capture_mission_document(
                "mission/tasks",
                author="AGENT",
                phase="structure",
            )
            if execution.block is not None:
                return self._block(running, str(execution.block))
            structure_error = self._structure_error()
            if structure_error:
                return self._block(running, structure_error)
            review = running.move_to(MissionStage.WORKPLAN_REVIEW)
            self._save(running, review)
            return PreparationResult(review)

    def approve_execution(self, *, expected_session_revision: int) -> PreparationResult:
        with self._action_lock:
            current = self._expected(
                expected_session_revision,
                MissionStage.WORKPLAN_REVIEW,
                "approve_execution",
            )
            documents = {
                item.logical_id: item.revision
                for item in self.catalog.list_latest()
                if item.logical_id.startswith("mission/")
            }
            approval = {
                "mission_id": current.mission_id,
                "snapshot_id": current.approved_snapshot_id,
                "session_revision": current.revision,
                "document_revisions": documents,
                "approved_at": datetime.now(timezone.utc).isoformat(),
            }
            self.services.artifacts.write_text(
                "execution_approval.json",
                json.dumps(approval, indent=2, ensure_ascii=False) + "\n",
            )
            ready = current.move_to(MissionStage.READY)
            self._save(current, ready)
            self.services.events.publish("execution_approved", approval)
            return PreparationResult(ready)

    def request_amendment(
        self,
        *,
        expected_session_revision: int,
        reason: str = "",
    ) -> PreparationResult:
        with self._action_lock:
            current = self._expected(
                expected_session_revision,
                (MissionStage.READY, MissionStage.TASK_REVIEW, MissionStage.PAUSED),
                "request_amendment",
            )
            review = current.move_to(
                MissionStage.AMENDMENT_REVIEW,
                active_phase="amendment_review",
            )
            self._save(current, review)
            self.services.events.publish(
                "amendment_requested",
                {"reason": reason, "session_revision": review.revision},
            )
            return PreparationResult(review)

    def _expected(
        self,
        expected_revision: int,
        stages: MissionStage | tuple[MissionStage, ...],
        action: str,
    ) -> MissionSession:
        current = self.session()
        if current.revision != expected_revision:
            raise SessionConflictError(current.revision)
        allowed = (stages,) if isinstance(stages, MissionStage) else stages
        if current.stage not in allowed:
            raise InvalidSessionAction(current.stage, action)
        return current

    def _save(self, previous: MissionSession, updated: MissionSession) -> None:
        self.sessions.save(updated, expected_revision=previous.revision)
        self.services.events.publish(
            "session_updated",
            {
                "mission_id": updated.mission_id,
                "revision": updated.revision,
                "stage": updated.stage.value,
                "active_phase": updated.active_phase,
                "active_task_id": updated.active_task_id,
            },
        )

    def _block(self, running: MissionSession, detail: str) -> PreparationResult:
        blocked = running.move_to(MissionStage.BLOCKED, blocked_reason=detail)
        self._save(running, blocked)
        return PreparationResult(blocked, False, detail)

    def _structure_error(self) -> str:
        try:
            tasks = self.services.tasks.load()
        except Exception as error:
            return str(error)
        if not tasks:
            return "tasks.json is empty"
        raw = self.services.artifacts.read_text("changeset.json", default="")
        if not raw:
            return ""
        operation_ids = [item["id"] for item in json.loads(raw).get("operations", [])]
        errors = validate_plan(operation_ids, tasks)
        return "; ".join(errors)

    def design_revision(self) -> int:
        return DesignStore(self.context.harness_dir / "design.db").current_revision()
