from __future__ import annotations

from typing import Protocol

from mission_orchestrator.domain.conversation import ConversationMessage, ConversationRole


class ConversationLog(Protocol):
    def append(self, role: ConversationRole, content: str, *, phase: str) -> ConversationMessage: ...
    def messages(self, *, after_sequence: int = 0, limit: int = 500) -> list[ConversationMessage]: ...


class NullConversationLog:
    def append(self, role: ConversationRole, content: str, *, phase: str) -> ConversationMessage:
        return ConversationMessage(0, "", role, phase, content, "")

    def messages(self, *, after_sequence: int = 0, limit: int = 500) -> list[ConversationMessage]:
        return []