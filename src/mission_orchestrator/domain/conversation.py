from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ConversationRole(Enum):
    HUMAN = "HUMAN"
    AGENT = "AGENT"
    SYSTEM = "SYSTEM"


@dataclass(frozen=True)
class ConversationMessage:
    sequence: int
    message_id: str
    role: ConversationRole
    phase: str
    content: str
    created_at: str

    def to_json(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "message_id": self.message_id,
            "role": self.role.value,
            "phase": self.phase,
            "content": self.content,
            "created_at": self.created_at,
        }