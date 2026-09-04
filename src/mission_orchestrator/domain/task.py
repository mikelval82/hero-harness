from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


def normalize_task_id(value: object) -> str:
    """Normalize the common model-generated ``task:`` ID prefix."""
    task_id = str(value or "").strip()
    return task_id.removeprefix("task:")


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
    BLOCKED = "blocked"

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
    covers: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    target_nodes: list[str] = field(default_factory=list)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Task":
        return cls(
            id=normalize_task_id(data.get("id", "")),
            title=str(data.get("title", "")).strip(),
            complexity=TaskComplexity.parse(data.get("complexity", TaskComplexity.M.value)),
            status=TaskStatus.parse(data.get("status", TaskStatus.PENDING.value)),
            failure_reason=str(data.get("failure_reason", "")),
            covers=[str(item) for item in data.get("covers", []) or []],
            dependencies=[normalize_task_id(item) for item in data.get("dependencies", []) or []],
            target_nodes=[str(item) for item in data.get("target_nodes", []) or []],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "complexity": self.complexity.value,
            "status": self.status.value,
            "failure_reason": self.failure_reason,
            "covers": list(self.covers),
            "dependencies": list(self.dependencies),
            "target_nodes": list(self.target_nodes),
        }


def summarize_tasks(tasks: list[Task]) -> str:
    total = len(tasks)
    completed = sum(1 for task in tasks if task.status == TaskStatus.COMPLETED)
    failed = sum(1 for task in tasks if task.status == TaskStatus.FAILED)
    blocked = sum(1 for task in tasks if task.status == TaskStatus.BLOCKED)
    pending = total - completed - failed - blocked
    lines = [
        f"Total: {total} | Completed: {completed} | Failed: {failed} | Blocked: {blocked} | Pending: {pending}"
    ]
    for task in tasks:
        if task.status == TaskStatus.FAILED:
            lines.append(f"FAILED [{task.id}]: {task.failure_reason or 'unknown'}")
        elif task.status == TaskStatus.BLOCKED:
            lines.append(f"BLOCKED [{task.id}]: {task.failure_reason or 'unknown'}")
    return "\n".join(lines)
