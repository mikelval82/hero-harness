from __future__ import annotations

from mission_orchestrator.adapters.telegram.api import send_message
from mission_orchestrator.domain.result import MissionOutcome, MissionResult


class TelegramNotifier:
    def __init__(self, token: str | None, chat_id: str | None, prefix: str = "") -> None:
        self.token = token
        self.chat_id = chat_id
        self.prefix = prefix.strip()

    def notify(self, message: str) -> None:
        text = f"{self.prefix} {message}".strip()
        print(text)
        if self.token and self.chat_id:
            send_message(self.token, self.chat_id, text)

    def notify_result(self, result: MissionResult) -> None:
        label = {
            MissionOutcome.BLOCKED: "BLOCKED",
            MissionOutcome.PARTIAL: "PARTIAL",
            MissionOutcome.COMPLETE: "COMPLETE",
        }[result.outcome]
        parts = [f"{label}", result.summary]
        if result.block:
            parts.append(f"Block: {result.block}")
        if result.report_preview:
            parts.append(result.report_preview)
        self.notify("\n\n".join(parts))


class NullNotifier:
    def notify(self, message: str) -> None:
        print(message)

    def notify_result(self, result: MissionResult) -> None:
        print(f"{result.outcome.value}: {result.summary}")

