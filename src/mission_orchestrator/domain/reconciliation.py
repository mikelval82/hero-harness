from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum

from mission_orchestrator.domain.task import Task, TaskStatus


class OperationState(Enum):
    PENDING = "pending"
    MATERIALIZED = "materialized"
    DIVERGENT = "divergent"
    UNVERIFIABLE = "unverifiable"


@dataclass(frozen=True)
class OperationCheck:
    operation_id: str
    state: OperationState
    detail: str
    blocking: bool = False


@dataclass(frozen=True)
class Reconciliation:
    snapshot_id: str
    observed_revision: int
    checks: tuple[OperationCheck, ...]

    def to_json(self) -> str:
        return json.dumps(
            {
                "snapshot_id": self.snapshot_id,
                "observed_revision": self.observed_revision,
                "checks": [
                    {
                        "operation_id": check.operation_id,
                        "state": check.state.value,
                        "detail": check.detail,
                        "blocking": check.blocking,
                    }
                    for check in self.checks
                ],
            },
            indent=2,
            ensure_ascii=False,
        )


def reconcile(
    changeset: dict,
    tasks: list[Task],
    observed_ids: set[str],
    observed_revision: int,
) -> Reconciliation:
    covering: dict[str, Task] = {}
    for task in tasks:
        for operation_id in task.covers:
            covering.setdefault(operation_id, task)

    checks: list[OperationCheck] = []
    for operation in changeset.get("operations", []):
        checks.append(_check(operation, covering.get(operation["id"]), observed_ids))
    return Reconciliation(
        snapshot_id=str(changeset.get("snapshot_id", "")),
        observed_revision=observed_revision,
        checks=tuple(checks),
    )


def _check(operation: dict, task: Task | None, observed_ids: set[str]) -> OperationCheck:
    operation_id = str(operation["id"])
    blocking = operation.get("verification_level") == "hard"
    if task is None:
        return OperationCheck(
            operation_id,
            OperationState.PENDING,
            "approved but uncovered by any task",
            blocking,
        )
    if task.status is not TaskStatus.COMPLETED:
        return OperationCheck(
            operation_id,
            OperationState.PENDING,
            f"covering task {task.id} is {task.status.value}",
            blocking,
        )
    kind = str(operation.get("kind", ""))
    locator = operation.get("locator")
    observed = bool(locator) and locator in observed_ids
    if kind == "CREATE_NODE":
        if not locator:
            return OperationCheck(
                operation_id,
                OperationState.UNVERIFIABLE,
                "no expected locator to observe",
                blocking,
            )
        if observed:
            return OperationCheck(
                operation_id,
                OperationState.MATERIALIZED,
                f"observed: {locator}",
                blocking,
            )
        return OperationCheck(
            operation_id,
            OperationState.DIVERGENT,
            f"expected symbol not observed: {locator}",
            blocking,
        )
    if kind == "MODIFY_NODE":
        if observed:
            return OperationCheck(
                operation_id,
                OperationState.MATERIALIZED,
                f"anchor still observed: {locator}",
                blocking,
            )
        return OperationCheck(
            operation_id,
            OperationState.DIVERGENT,
            f"anchor disappeared: {locator}",
            blocking,
        )
    if kind == "REMOVE_NODE":
        if not observed:
            return OperationCheck(
                operation_id,
                OperationState.MATERIALIZED,
                f"no longer observed: {locator}",
                blocking,
            )
        return OperationCheck(
            operation_id,
            OperationState.DIVERGENT,
            f"target still observed: {locator}",
            blocking,
        )
    return OperationCheck(
        operation_id,
        OperationState.UNVERIFIABLE,
        "relation is not observed by the graph reconciler",
        blocking,
    )


def merge_gate_reasons(reconciliation: Reconciliation, tasks: list[Task]) -> list[str]:
    reasons: list[str] = []
    for task in tasks:
        if task.status is TaskStatus.FAILED:
            reasons.append(f"task failed: {task.id}")
        elif task.status is TaskStatus.BLOCKED:
            reasons.append(f"task blocked: {task.id}")
    for check in reconciliation.checks:
        if check.state is OperationState.PENDING:
            reasons.append(f"operation not materialized: {check.operation_id} ({check.detail})")
        elif check.state is OperationState.DIVERGENT:
            reasons.append(f"divergence: {check.operation_id} ({check.detail})")
        elif check.state is OperationState.UNVERIFIABLE and check.blocking:
            reasons.append(f"required operation unverifiable: {check.operation_id} ({check.detail})")
    return reasons
