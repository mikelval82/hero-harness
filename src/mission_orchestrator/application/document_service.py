from __future__ import annotations

import hashlib

from mission_orchestrator.domain.document import DocumentSaveResult, DocumentSaveStatus
from mission_orchestrator.ports.artifacts import ArtifactStore
from mission_orchestrator.ports.documents import DocumentCatalog
from mission_orchestrator.ports.events import EventPublisher


MISSION_DOCUMENTS = {
    "mission/idea": "idea.md",
    "mission/brief-seed": "brief-seed.md",
    "mission/brainstorm": "brainstorm.md",
    "mission/brief": "brief.md",
    "mission/tasks": "tasks.json",
    "mission/report": "mission-report.md",
}
TASK_DOCUMENTS = {
    "contract": "task-contract.json",
    "spec": "spec.md",
    "plan": "plan.md",
    "decisions": "decisions.md",
    "status": "status.md",
    "audit": "audit.md",
    "reconciliation": "reconciliation.json",
    "verification": "contract-verification.json",
}


def task_document_id(task_id: str, kind: str) -> str:
    if kind not in TASK_DOCUMENTS:
        raise ValueError(f"unknown task document kind: {kind}")
    normalized = task_id.strip().lower()
    if not normalized:
        raise ValueError("task_id must not be empty")
    return f"task/{normalized}/{kind}"


class MissionDocumentService:
    def __init__(
        self,
        artifacts: ArtifactStore,
        catalog: DocumentCatalog,
        events: EventPublisher,
    ) -> None:
        self.artifacts = artifacts
        self.catalog = catalog
        self.events = events

    def save(
        self,
        *,
        logical_id: str,
        alias: str | None,
        content: str,
        author: str,
        base_revision: int,
        command_id: str,
        phase: str = "",
        task_id: str = "",
    ) -> DocumentSaveResult:
        result = self.catalog.save(
            logical_id=logical_id,
            content=content,
            author=author,
            base_revision=base_revision,
            command_id=command_id,
            phase=phase,
            task_id=task_id,
        )
        if result.status is DocumentSaveStatus.APPLIED:
            if alias is not None:
                self.artifacts.write_text(alias, content)
            self.events.publish(
                "document_version_created",
                {
                    "logical_id": logical_id,
                    "revision": result.revision,
                    "author": author,
                    "phase": phase,
                    "task_id": task_id,
                },
            )
        return result

    def capture_alias(
        self,
        *,
        logical_id: str,
        alias: str,
        author: str,
        phase: str = "",
        task_id: str = "",
    ) -> DocumentSaveResult | None:
        content = self.artifacts.read_text(alias, default="")
        if not content:
            return None
        current = self.catalog.get(logical_id)
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if current is not None and current.content_hash == content_hash:
            return DocumentSaveResult(
                DocumentSaveStatus.DUPLICATE,
                current.revision,
                current.revision,
            )
        base_revision = current.revision if current is not None else 0
        return self.save(
            logical_id=logical_id,
            alias=alias,
            content=content,
            author=author,
            base_revision=base_revision,
            command_id=f"capture:{logical_id}:{content_hash}",
            phase=phase,
            task_id=task_id,
        )

    def capture_mission_document(self, logical_id: str, *, author: str, phase: str) -> DocumentSaveResult | None:
        try:
            alias = MISSION_DOCUMENTS[logical_id]
        except KeyError as error:
            raise ValueError(f"unknown mission document: {logical_id}") from error
        return self.capture_alias(
            logical_id=logical_id,
            alias=alias,
            author=author,
            phase=phase,
        )

    @staticmethod
    def alias_for(logical_id: str) -> tuple[str, str]:
        if logical_id in MISSION_DOCUMENTS:
            return MISSION_DOCUMENTS[logical_id], ""
        parts = logical_id.split("/")
        if len(parts) == 3 and parts[0] == "task" and parts[1] and parts[2] in TASK_DOCUMENTS:
            return TASK_DOCUMENTS[parts[2]], parts[1]
        raise ValueError(f"unknown logical document: {logical_id}")

    def capture_task_documents(self, task_id: str) -> list[DocumentSaveResult]:
        results = []
        for kind, alias in TASK_DOCUMENTS.items():
            result = self.capture_alias(
                logical_id=task_document_id(task_id, kind),
                alias=alias,
                author="AGENT",
                phase=kind,
                task_id=task_id,
            )
            if result is not None:
                results.append(result)
        return results
