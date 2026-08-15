from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DocumentSaveStatus(Enum):
    APPLIED = "APPLIED"
    CONFLICT = "CONFLICT"
    DUPLICATE = "DUPLICATE"


@dataclass(frozen=True)
class DocumentVersion:
    logical_id: str
    revision: int
    content: str
    content_hash: str
    author: str
    phase: str
    task_id: str
    created_at: str

    def metadata(self) -> dict[str, object]:
        return {
            "logical_id": self.logical_id,
            "revision": self.revision,
            "content_hash": self.content_hash,
            "author": self.author,
            "phase": self.phase,
            "task_id": self.task_id,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class DocumentSaveResult:
    status: DocumentSaveStatus
    revision: int
    current_revision: int
    detail: str = ""