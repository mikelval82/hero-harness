from __future__ import annotations

from mission_orchestrator.adapters.filesystem.logger import describe_tool_call
from mission_orchestrator.domain.result import MissionResult
from mission_orchestrator.ports.events import EventPublisher
from mission_orchestrator.ports.logger import MissionLogger
from mission_orchestrator.ports.notifier import Notifier


def _safe_publish(events: EventPublisher, kind: str, payload: dict) -> None:
    try:
        events.publish(kind, payload)
    except Exception:
        pass


class PublishingNotifier:
    def __init__(self, inner: Notifier, events: EventPublisher) -> None:
        self.inner = inner
        self.events = events

    def notify(self, message: str) -> None:
        _safe_publish(self.events, "notification", {"message": message})
        self.inner.notify(message)

    def notify_result(self, result: MissionResult) -> None:
        _safe_publish(
            self.events,
            "mission_result",
            {
                "outcome": result.outcome.value,
                "summary": result.summary,
                "completed": result.completed,
                "failed": result.failed,
            },
        )
        self.inner.notify_result(result)


class PublishingLogger:
    def __init__(self, inner: MissionLogger, events: EventPublisher) -> None:
        self.inner = inner
        self.events = events

    def log(self, message: str) -> None:
        self.inner.log(message)

    def tool_call(self, name: str, input: dict) -> None:
        _safe_publish(self.events, "tool_call", {"tool": name, "summary": describe_tool_call(name, input)})
        self.inner.tool_call(name, input)

    def metric(self, record: dict) -> None:
        kind = record.get("event") or ("phase" if "phase" in record else "metric")
        _safe_publish(self.events, kind, record)
        self.inner.metric(record)
