from __future__ import annotations

from typing import Protocol

from mission_orchestrator.domain.document import DocumentSaveResult, DocumentVersion


class DocumentCatalog(Protocol):
    def save(
        self,
        *,
        logical_id: str,
        content: str,
        author: str,
        base_revision: int,
        command_id: str,
        phase: str = "",
        task_id: str = "",
    ) -> DocumentSaveResult: ...

    def get(self, logical_id: str, revision: int | None = None) -> DocumentVersion | None: ...
    def list_latest(self) -> list[DocumentVersion]: ...