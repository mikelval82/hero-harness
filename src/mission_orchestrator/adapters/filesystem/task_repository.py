from __future__ import annotations

import json

from mission_orchestrator.domain.task import Task, TaskStatus, summarize_tasks
from mission_orchestrator.ports.artifacts import ArtifactStore


class JsonTaskRepository:
    def __init__(self, artifacts: ArtifactStore, artifact_name: str = "tasks.json") -> None:
        self.artifacts = artifacts
        self.artifact_name = artifact_name

    def load(self) -> list[Task]:
        raw = self.artifacts.read_text(self.artifact_name)
        data = json.loads(raw)
        if not isinstance(data, list):
            raise ValueError("tasks.json must contain a JSON list")
        tasks = [Task.from_json(item) for item in data if isinstance(item, dict)]
        if len(tasks) != len(data):
            raise ValueError("every tasks.json item must be an object")
        for task in tasks:
            if not task.id or not task.title:
                raise ValueError("every task must have id and title")
        return tasks

    def save(self, tasks: list[Task]) -> None:
        data = [task.to_json() for task in tasks]
        self.artifacts.write_text(self.artifact_name, json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    def update(self, index: int, status: TaskStatus, reason: str = "") -> None:
        tasks = self.load()
        tasks[index].status = status
        tasks[index].failure_reason = reason
        self.save(tasks)

    def summary(self) -> str:
        return summarize_tasks(self.load())

