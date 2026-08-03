from __future__ import annotations

from mission_orchestrator.domain.task import Task


def validate_plan(operation_ids: list[str], tasks: list[Task]) -> list[str]:
    errors: list[str] = []
    expected = set(operation_ids)
    task_ids = {task.id for task in tasks}

    coverage: dict[str, list[str]] = {}
    for task in tasks:
        for operation in task.covers:
            coverage.setdefault(operation, []).append(task.id)
        for dependency in task.dependencies:
            if dependency == task.id:
                errors.append(f"task {task.id} depends on itself")
            elif dependency not in task_ids:
                errors.append(f"task {task.id} depends on unknown task {dependency}")

    for operation in sorted(expected):
        owners = coverage.get(operation, [])
        if not owners:
            errors.append(f"operation not covered by any task: {operation}")
        elif len(owners) > 1:
            errors.append(f"operation covered more than once: {operation} ({', '.join(sorted(owners))})")

    for operation, owners in sorted(coverage.items()):
        if operation not in expected:
            errors.append(f"task {owners[0]} covers unknown operation: {operation}")

    errors.extend(_find_cycles(tasks, task_ids))
    return errors


def _find_cycles(tasks: list[Task], task_ids: set[str]) -> list[str]:
    graph = {task.id: [dep for dep in task.dependencies if dep in task_ids] for task in tasks}
    state: dict[str, int] = {}
    stack: list[str] = []
    cycles: list[str] = []

    def visit(node: str) -> None:
        state[node] = 1
        stack.append(node)
        for neighbor in graph.get(node, []):
            if state.get(neighbor, 0) == 1:
                start = stack.index(neighbor)
                cycles.append("dependency cycle: " + " -> ".join([*stack[start:], neighbor]))
            elif state.get(neighbor, 0) == 0:
                visit(neighbor)
        stack.pop()
        state[node] = 2

    for task in tasks:
        if state.get(task.id, 0) == 0:
            visit(task.id)
    return cycles
