from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field

from mission_orchestrator.adapters.analysis.sqlite_graph import SQLiteCodeGraph
from mission_orchestrator.adapters.design.store import DesignStore
from mission_orchestrator.application.code_graph_queries import query_mission_code_graph
from mission_orchestrator.application.code_questions import CodeQuestionService
from mission_orchestrator.application.contract_execution import ContractExecutionService
from mission_orchestrator.application.document_service import MissionDocumentService
from mission_orchestrator.application.interactive_task_coordinator import InteractiveTaskCoordinator
from mission_orchestrator.application.preparation_coordinator import PreparationCoordinator, PreparationResult
from mission_orchestrator.application.services import AppServices
from mission_orchestrator.domain.command import parse_control_command
from mission_orchestrator.domain.design import ApplyStatus, Location, Resolution
from mission_orchestrator.domain.document import DocumentSaveResult
from mission_orchestrator.domain.mission import MissionContext
from mission_orchestrator.domain.session import MissionStage
from mission_orchestrator.ports.conversation import ConversationLog, NullConversationLog
from mission_orchestrator.ports.documents import DocumentCatalog
from mission_orchestrator.ports.session_store import MissionSessionStore, SessionConflictError


@dataclass(frozen=True)
class MissionControlPlane:
    services: AppServices
    context: MissionContext
    sessions: MissionSessionStore
    catalog: DocumentCatalog
    documents: MissionDocumentService
    preparation: PreparationCoordinator
    tasks: InteractiveTaskCoordinator
    conversation: ConversationLog = field(default_factory=NullConversationLog)
    executions: ContractExecutionService | None = None
    questions: CodeQuestionService | None = None

    def capabilities(self) -> dict[str, object]:
        return {
            "api_version": "v1",
            "actions": [
                "research",
                "grill",
                "approve-design",
                "approve-execution",
                "request-amendment",
                "prepare-task",
                "execute-task",
                "retry-review",
            ],
            "features": {
                "versioned_documents": True,
                "design_cas": True,
                "conversation": True,
                "long_poll_events": True,
                "interactive_task_gates": True,
                "safe_design_amendments": True,
                "contract_execution": True,
                "code_graph_queries": True,
                "read_only_ask": self.questions is not None,
            },
            "event_wait_seconds": 30,
        }

    def snapshot(self) -> dict[str, object]:
        session = self.sessions.load(self.context.mission_tag)
        try:
            tasks = [task.to_json() for task in self.services.tasks.load()]
        except Exception:
            tasks = []
        design = DesignStore(self.context.harness_dir / "design.db")
        facts = self._facts()
        return {
            "api_version": "v1",
            "mission": session.to_json()
            | {
                "project_name": self.context.project_name,
                "project_dir": str(self.context.project_dir),
                "branch": self.context.branch,
                "mode": self.context.mode.value,
            },
            "tasks": tasks,
            "documents": [item.metadata() for item in self.catalog.list_latest()],
            "design": {
                "design_revision": design.current_revision(),
                "observed_revision": facts.observed_revision() if facts is not None else 0,
                "approved_snapshot_id": session.approved_snapshot_id,
            },
            "contract_execution": self._execution_service().current_execution(),
        }

    def code_graph_query(self, request: dict) -> dict[str, object]:
        return query_mission_code_graph(self.context.harness_dir, request)

    def ask(self, question: str) -> dict[str, object]:
        return self._question_service().submit(question)

    def ask_operation(self, operation_id: str) -> dict[str, object]:
        return self._question_service().get(operation_id)

    def contract_tasks(self) -> dict[str, object]:
        return self._execution_service().list_tasks()

    def contract_task(self, task_id: str) -> dict[str, object]:
        return self._execution_service().get_task(task_id)

    def begin_contract_execution(self, *, task_id: str, actor: str) -> dict[str, object]:
        return self._execution_service().begin(task_id=task_id, actor=actor)

    def validate_contract_execution(self, execution_id: str) -> dict[str, object]:
        return self._execution_service().validate(execution_id)

    def read_contract_file(self, execution_id: str, path: str) -> dict[str, object]:
        return self._execution_service().read_file(execution_id, path)

    def apply_contract_patch(
        self,
        execution_id: str,
        *,
        path: str,
        expected_sha256: str,
        old_text: str,
        new_text: str,
    ) -> dict[str, object]:
        return self._execution_service().apply_patch(
            execution_id,
            path=path,
            expected_sha256=expected_sha256,
            old_text=old_text,
            new_text=new_text,
        )

    def run_contract_checks(self, execution_id: str) -> dict[str, bool]:
        return self._execution_service().run_checks(execution_id)

    def complete_contract_execution(self, execution_id: str) -> dict[str, object]:
        return self._execution_service().complete(execution_id)

    def report_contract_blocker(self, execution_id: str, detail: str) -> dict[str, object]:
        return self._execution_service().report_blocker(execution_id, detail)

    def propose_contract_amendment(self, execution_id: str, detail: str) -> dict[str, object]:
        result = self._execution_service().propose_amendment(execution_id, detail)
        current = self.sessions.load(self.context.mission_tag)
        preparation = self.preparation.request_amendment(
            expected_session_revision=current.revision,
            reason=detail,
        )
        return result | {"session": preparation.session.to_json()}

    def document(self, logical_id: str, revision: int | None = None) -> dict[str, object] | None:
        document = self.catalog.get(logical_id, revision)
        if document is None:
            return None
        return document.metadata() | {"content": document.content}

    def save_document(
        self,
        *,
        logical_id: str,
        content: str,
        base_revision: int,
        command_id: str,
    ) -> DocumentSaveResult:
        alias, task_id = self.documents.alias_for(logical_id)
        session = self.sessions.load(self.context.mission_tag)
        selected_alias = alias
        if task_id and session.active_task_id.lower() != task_id.lower():
            selected_alias = None
        return self.documents.save(
            logical_id=logical_id,
            alias=selected_alias,
            content=content,
            author="HUMAN",
            base_revision=base_revision,
            command_id=command_id,
            phase=logical_id.rsplit("/", 1)[-1],
            task_id=task_id.upper(),
        )

    def design(self) -> dict[str, object]:
        store = DesignStore(self.context.harness_dir / "design.db")
        facts = self._facts()
        nodes = []
        for node in store.nodes():
            if node.location == Location.EXTERNAL.value:
                resolution = Resolution.EXTERNAL
            elif facts is None or not node.locator:
                resolution = Resolution.UNRESOLVED
            else:
                resolution = store.resolution_for(node, facts)
            nodes.append(node.__dict__ | {"resolution": resolution.value})
        return {
            "design_revision": store.current_revision(),
            "observed_revision": facts.observed_revision() if facts is not None else 0,
            "nodes": nodes,
            "edges": [edge.__dict__ for edge in store.edges()],
            "history": [
                {
                    "seq": item.seq,
                    "operation_id": item.operation_id,
                    "author": item.author,
                    "base_revision": item.base_revision,
                    "status": item.status.value,
                    "detail": item.detail,
                }
                for item in store.history()
            ],
        }

    def apply_design(
        self,
        *,
        base_revision: int,
        operations: list[dict],
        operation_id: str = "",
    ) -> dict[str, object]:
        selected_id = operation_id or f"human-{uuid.uuid4().hex}"
        store = DesignStore(self.context.harness_dir / "design.db")
        result = store.apply(
            operation_id=selected_id,
            author="HUMAN",
            base_revision=base_revision,
            operations=operations,
        )
        payload = {
            "operation_id": selected_id,
            "status": result.status.value,
            "design_revision": result.revision,
            "detail": result.detail,
        }
        if result.status is ApplyStatus.APPLIED:
            payload["amendment"] = self._record_design_amendment(result.revision)
        self.services.events.publish("design_changed", payload)
        return payload

    def run_action(self, action: str, body: dict) -> PreparationResult:
        revision = self._required_int(body, "expected_session_revision")
        if action == "research":
            return self.preparation.run_research(expected_session_revision=revision)
        if action == "grill":
            return self.preparation.run_grill(expected_session_revision=revision)
        if action == "approve-design":
            return self.preparation.approve_design_and_structure(
                expected_session_revision=revision,
                base_design_revision=self._required_int(body, "base_design_revision"),
                base_brief_revision=self._optional_int(body, "base_brief_revision"),
            )
        if action == "approve-execution":
            return self.preparation.approve_execution(expected_session_revision=revision)
        if action == "request-amendment":
            return self.preparation.request_amendment(
                expected_session_revision=revision,
                reason=str(body.get("reason", "")),
            )
        if action == "prepare-task":
            return self.tasks.prepare_next(expected_session_revision=revision)
        if action == "execute-task":
            return self.tasks.execute_prepared(
                expected_session_revision=revision,
                task_id=str(body.get("task_id", "")),
            )
        if action == "retry-review":
            return self.tasks.retry_review(expected_session_revision=revision)
        raise ValueError(f"unknown action: {action}")

    def submit_command(self, text: str) -> dict[str, object]:
        command = parse_control_command(text)
        if command is None:
            raise ValueError("empty or unknown command")
        self.services.commands.publish(command)
        return {"accepted": True, "kind": command.kind.value}

    def messages(self, *, after_sequence: int = 0) -> dict[str, object]:
        messages = self.conversation.messages(after_sequence=after_sequence)
        return {"messages": [message.to_json() for message in messages]}

    def _facts(self) -> SQLiteCodeGraph | None:
        path = self.context.harness_dir / "code_graph.db"
        return SQLiteCodeGraph(path) if path.exists() else None

    def _execution_service(self) -> ContractExecutionService:
        return self.executions or ContractExecutionService(
            services=self.services,
            context=self.context,
            sessions=self.sessions,
        )

    def _question_service(self) -> CodeQuestionService:
        if self.questions is None:
            raise ValueError("read-only ask is not available")
        return self.questions

    def _record_design_amendment(self, design_revision: int) -> str:
        current = self.sessions.load(self.context.mission_tag)
        if current.stage in {MissionStage.EXECUTING, MissionStage.RECONCILING}:
            self.services.artifacts.write_text(
                "_amendment_pending.json",
                json.dumps(
                    {
                        "design_revision": design_revision,
                        "requested_session_revision": current.revision,
                    },
                    indent=2,
                )
                + "\n",
            )
            self.services.events.publish(
                "amendment_pending",
                {"design_revision": design_revision},
            )
            return "pending_safe_boundary"
        if current.stage not in {
            MissionStage.READY,
            MissionStage.TASK_REVIEW,
            MissionStage.PAUSED,
        }:
            return "not_required"
        review = current.move_to(
            MissionStage.AMENDMENT_REVIEW,
            active_phase="amendment_review",
        )
        try:
            self.sessions.save(review, expected_revision=current.revision)
        except SessionConflictError:
            self.services.artifacts.write_text(
                "_amendment_pending.json",
                json.dumps({"design_revision": design_revision}, indent=2) + "\n",
            )
            return "pending_safe_boundary"
        self.services.events.publish(
            "session_updated",
            {
                "mission_id": review.mission_id,
                "revision": review.revision,
                "stage": review.stage.value,
                "active_phase": review.active_phase,
                "active_task_id": review.active_task_id,
            },
        )
        self.services.events.publish(
            "amendment_requested",
            {"design_revision": design_revision, "session_revision": review.revision},
        )
        return "required"

    @staticmethod
    def _required_int(body: dict, key: str) -> int:
        value = body.get(key)
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"{key} must be an integer")
        return value

    @staticmethod
    def _optional_int(body: dict, key: str) -> int | None:
        value = body.get(key)
        if value is None:
            return None
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"{key} must be an integer")
        return value


def control_plane_for(runtime) -> MissionControlPlane:  # noqa: ANN001
    from mission_orchestrator.adapters.conversation.sqlite_log import SqliteConversationLog
    from mission_orchestrator.adapters.documents.sqlite_catalog import SqliteDocumentCatalog
    from mission_orchestrator.adapters.filesystem.session_store import FilesystemMissionSessionStore

    sessions = FilesystemMissionSessionStore(runtime.services.artifacts)
    catalog = SqliteDocumentCatalog(runtime.context.harness_dir / "documents.db")
    documents = MissionDocumentService(runtime.services.artifacts, catalog, runtime.services.events)
    return MissionControlPlane(
        services=runtime.services,
        context=runtime.context,
        sessions=sessions,
        catalog=catalog,
        documents=documents,
        preparation=PreparationCoordinator(
            services=runtime.services,
            context=runtime.context,
            sessions=sessions,
            documents=documents,
            catalog=catalog,
        ),
        tasks=InteractiveTaskCoordinator(
            services=runtime.services,
            context=runtime.context,
            sessions=sessions,
            documents=documents,
        ),
        conversation=SqliteConversationLog(runtime.context.harness_dir / "conversation.db"),
        executions=ContractExecutionService(
            services=runtime.services,
            context=runtime.context,
            sessions=sessions,
        ),
        questions=CodeQuestionService(runtime.services, runtime.context),
    )
