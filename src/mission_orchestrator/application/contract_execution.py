from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone

from mission_orchestrator.application.contract_verifier import PythonContractVerifier
from mission_orchestrator.application.services import AppServices
from mission_orchestrator.domain.mission import MissionContext
from mission_orchestrator.domain.session import MissionStage
from mission_orchestrator.domain.task import TaskStatus
from mission_orchestrator.ports.session_store import MissionSessionStore


EXECUTION_STATE = "contract-executions.json"
CONTRACT_INDEX = "task-contracts/index.json"
EXECUTION_ACTORS = {"mission", "chat", "mcp"}


class ExecutionConflictError(RuntimeError):
    pass


class ExecutionValidationError(RuntimeError):
    pass


class ContractExecutionService:
    """Owns task-contract retrieval, the single lease, and verification evidence."""

    def __init__(
        self,
        *,
        services: AppServices,
        context: MissionContext,
        sessions: MissionSessionStore,
    ) -> None:
        self.services = services
        self.context = context
        self.sessions = sessions
        self._lock = threading.RLock()

    def list_tasks(self) -> dict[str, object]:
        index = self._index()
        execution = self.current_execution()
        tasks = []
        for task in self.services.tasks.load():
            if task.id not in index["contracts"]:
                continue
            tasks.append(
                {
                    "id": task.id,
                    "title": task.title,
                    "status": task.status.value,
                    "dependencies": list(task.dependencies),
                    "contract_path": index["contracts"][task.id],
                    "execution": (
                        execution
                        if execution is not None and execution.get("task_id") == task.id
                        else None
                    ),
                }
            )
        return {"snapshot_id": index["snapshot_id"], "tasks": tasks}

    def get_task(self, task_id: str) -> dict[str, object]:
        task = self._task(task_id)
        contract = self._contract(task_id)
        execution = self.current_execution()
        return {
            "task": task.to_json(),
            "contract": contract,
            "execution": (
                execution
                if execution is not None and execution.get("task_id") == task_id
                else None
            ),
        }

    def begin(self, *, task_id: str, actor: str) -> dict[str, object]:
        if actor not in EXECUTION_ACTORS:
            raise ValueError(f"invalid execution actor: {actor}")
        with self._lock:
            state = self._state()
            active = self._active(state)
            if active is not None:
                raise ExecutionConflictError(
                    f"execution lease already held by {active['execution_id']} ({active['actor']})"
                )
            session = self.sessions.load(self.context.mission_tag)
            if session.stage is not MissionStage.READY:
                raise ExecutionConflictError(
                    f"mission must be ready for external execution; current stage is {session.stage.value}"
                )
            task = self._task(task_id)
            if task.status is not TaskStatus.PENDING:
                raise ExecutionConflictError(f"task {task_id} is {task.status.value}")
            contract = self._contract(task_id)
            now = _now()
            execution: dict[str, object] = {
                "execution_id": uuid.uuid4().hex,
                "actor": actor,
                "task_id": task_id,
                "snapshot_id": str(contract.get("snapshot_id", "")),
                "branch": self.context.branch,
                "base_commit": str(contract.get("base_commit", "")),
                "start_commit": self.services.git.current_commit(),
                "started_at": now,
                "heartbeat_at": now,
                "status": "active",
                "changed_files": [],
                "final_commit": "",
                "verifier": None,
            }
            state["executions"].append(execution)
            self._save_state(state)
            self.services.events.publish("contract_execution_started", execution)
            return dict(execution)

    def validate(self, execution_id: str) -> dict[str, object]:
        with self._lock:
            state, execution = self._require_active(execution_id)
            contract = self._contract(str(execution["task_id"]))
            verification = PythonContractVerifier(self.context.project_dir).verify(contract)
            payload = json.loads(verification.to_json())
            artifact = f"contract-verifications/{execution_id}.json"
            encoded = verification.to_json() + "\n"
            self.services.artifacts.write_text(artifact, encoded)
            self.services.artifacts.write_text("contract-verification.json", encoded)
            execution["heartbeat_at"] = _now()
            execution["verifier"] = {
                "passed": verification.passed,
                "artifact": artifact,
                "failed_checks": sum(
                    1 for check in verification.checks if check.state.value == "failed"
                ),
            }
            self._save_state(state)
            self.services.events.publish(
                "contract_execution_validated",
                {
                    "execution_id": execution_id,
                    "task_id": execution["task_id"],
                    "passed": verification.passed,
                },
            )
            return payload

    def complete(self, execution_id: str) -> dict[str, object]:
        verification = self.validate(execution_id)
        if not verification["passed"]:
            failures = [
                f"{item['node_id']}.{item['field']}: {item['detail']}"
                for item in verification["checks"]
                if item["state"] == "failed"
            ]
            raise ExecutionValidationError("; ".join(failures))
        with self._lock:
            state, execution = self._require_active(execution_id)
            tasks = self.services.tasks.load()
            index = next(
                (position for position, task in enumerate(tasks) if task.id == execution["task_id"]),
                None,
            )
            if index is None:
                raise ValueError(f"unknown task: {execution['task_id']}")
            self.services.tasks.update(index, TaskStatus.COMPLETED)
            tasks[index].status = TaskStatus.COMPLETED
            current = self.sessions.load(self.context.mission_tag)
            updated = (
                current.move_to(MissionStage.COMPLETED, active_task_id="")
                if all(task.status is TaskStatus.COMPLETED for task in tasks)
                else current.touch()
            )
            self.sessions.save(updated, expected_revision=current.revision)
            execution.update(
                {
                    "status": "completed",
                    "heartbeat_at": _now(),
                    "ended_at": _now(),
                    "changed_files": self._changed_files(),
                    "final_commit": self.services.git.current_commit(),
                }
            )
            self._save_state(state)
            self.services.events.publish("contract_execution_completed", execution)
            return dict(execution)

    def report_blocker(self, execution_id: str, detail: str) -> dict[str, object]:
        if not detail.strip():
            raise ValueError("blocker detail must not be empty")
        return self._end(execution_id, "blocked", {"blocker": detail.strip()})

    def propose_amendment(self, execution_id: str, detail: str) -> dict[str, object]:
        if not detail.strip():
            raise ValueError("amendment detail must not be empty")
        return self._end(execution_id, "amendment_requested", {"amendment": detail.strip()})

    def current_execution(self) -> dict[str, object] | None:
        with self._lock:
            executions = self._state()["executions"]
            return dict(executions[-1]) if executions else None

    def _end(self, execution_id: str, status: str, fields: dict[str, object]) -> dict[str, object]:
        with self._lock:
            state, execution = self._require_active(execution_id)
            execution.update(fields | {"status": status, "heartbeat_at": _now(), "ended_at": _now()})
            self._save_state(state)
            self.services.events.publish(f"contract_execution_{status}", execution)
            return dict(execution)

    def _index(self) -> dict:
        raw = self.services.artifacts.read_text(CONTRACT_INDEX, default="")
        if not raw:
            raise ValueError("task contracts are not available; approve the WorkPlan first")
        index = json.loads(raw)
        if not isinstance(index, dict) or not isinstance(index.get("contracts"), dict):
            raise ValueError("task contract index is malformed")
        return index

    def _contract(self, task_id: str) -> dict:
        path = self._index()["contracts"].get(task_id)
        if not path:
            raise ValueError(f"task contract not found: {task_id}")
        contract = json.loads(self.services.artifacts.read_text(str(path)))
        if not isinstance(contract, dict):
            raise ValueError(f"task contract is malformed: {task_id}")
        return contract

    def _task(self, task_id: str):  # noqa: ANN202
        for task in self.services.tasks.load():
            if task.id == task_id:
                return task
        raise ValueError(f"unknown task: {task_id}")

    def _state(self) -> dict:
        raw = self.services.artifacts.read_text(EXECUTION_STATE, default="")
        if not raw:
            return {"schema_version": 1, "executions": []}
        state = json.loads(raw)
        if not isinstance(state, dict) or not isinstance(state.get("executions"), list):
            raise ValueError("contract execution state is malformed")
        return state

    def _save_state(self, state: dict) -> None:
        self.services.artifacts.write_text(
            EXECUTION_STATE,
            json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        )

    @staticmethod
    def _active(state: dict) -> dict | None:
        return next(
            (execution for execution in reversed(state["executions"]) if execution.get("status") == "active"),
            None,
        )

    def _require_active(self, execution_id: str) -> tuple[dict, dict]:
        state = self._state()
        active = self._active(state)
        if active is None or active.get("execution_id") != execution_id:
            raise ExecutionConflictError(f"execution is not the active lease: {execution_id}")
        return state, active

    def _changed_files(self) -> list[str]:
        method = getattr(self.services.git, "changed_files", None)
        return list(method()) if callable(method) else []


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
