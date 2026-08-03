from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class TaskComplexity(Enum):
    S = "S"
    M = "M"
    L = "L"

    @classmethod
    def parse(cls, value: object) -> "TaskComplexity":
        if isinstance(value, cls):
            return value
        text = str(value or cls.M.value).upper()
        return cls.__members__.get(text, cls.M)


class TaskStatus(Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"

    @classmethod
    def parse(cls, value: object) -> "TaskStatus":
        if isinstance(value, cls):
            return value
        text = str(value or cls.PENDING.value).lower()
        for status in cls:
            if status.value == text:
                return status
        return cls.PENDING


@dataclass
class Task:
    id: str
    title: str
    complexity: TaskComplexity = TaskComplexity.M
    status: TaskStatus = TaskStatus.PENDING
    failure_reason: str = ""

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Task":
        return cls(
            id=str(data.get("id", "")).strip(),
            title=str(data.get("title", "")).strip(),
            complexity=TaskComplexity.parse(data.get("complexity", TaskComplexity.M.value)),
            status=TaskStatus.parse(data.get("status", TaskStatus.PENDING.value)),
            failure_reason=str(data.get("failure_reason", "")),
        )

    def to_json(self) -> dict[str, str]:
        return {
            "id": self.id,
            "title": self.title,
            "complexity": self.complexity.value,
            "status": self.status.value,
            "failure_reason": self.failure_reason,
        }


def summarize_tasks(tasks: list[Task]) -> str:
    total = len(tasks)
    completed = sum(1 for task in tasks if task.status == TaskStatus.COMPLETED)
    failed = sum(1 for task in tasks if task.status == TaskStatus.FAILED)
    pending = total - completed - failed
    lines = [f"Total: {total} | Completed: {completed} | Failed: {failed} | Pending: {pending}"]
    for task in tasks:
        if task.status == TaskStatus.FAILED:
            reason = task.failure_reason or "unknown"
            lines.append(f"FAILED [{task.id}]: {reason}")
    return "\n".join(lines)

