from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class ChangeOperation:
    id: str
    kind: str
    target_node: str
    locator: str | None
    level: str
    location: str
    depends_on: tuple[str, ...]
    description: str


@dataclass(frozen=True)
class SkippedChange:
    target_node: str
    reason: str


@dataclass(frozen=True)
class ChangeIssue:
    target_node: str
    detail: str


@dataclass(frozen=True)
class ChangeSet:
    snapshot_id: str
    operations: tuple[ChangeOperation, ...]
    skipped: tuple[SkippedChange, ...]
    issues: tuple[ChangeIssue, ...]


def compile_changeset(snapshot: dict, observed_ids: set[str]) -> ChangeSet:
    operations: list[ChangeOperation] = []
    skipped: list[SkippedChange] = []
    issues: list[ChangeIssue] = []
    nodes = {node["id"]: node for node in snapshot.get("nodes", [])}

    for node in nodes.values():
        intent = node.get("intent", "KEEP")
        locator = node.get("locator")
        resolved = bool(locator) and locator in observed_ids
        if intent == "KEEP":
            continue
        if intent == "CREATE":
            if resolved:
                skipped.append(SkippedChange(node["id"], "already_materialized"))
                continue
            operations.append(_operation("create", "CREATE_NODE", node))
        elif intent == "CHANGE":
            if not locator:
                issues.append(ChangeIssue(node["id"], "CHANGE requires a locator anchoring observed code"))
                continue
            if not resolved:
                issues.append(ChangeIssue(node["id"], f"CHANGE target not observed: {locator}"))
                continue
            operations.append(_operation("change", "MODIFY_NODE", node))
        elif intent == "REMOVE":
            if not locator or not resolved:
                issues.append(ChangeIssue(node["id"], f"REMOVE target not observed: {locator or '(no locator)'}"))
                continue
            operations.append(_operation("remove", "REMOVE_NODE", node))

    create_ops = {op.target_node: op.id for op in operations if op.kind == "CREATE_NODE"}
    for edge in snapshot.get("edges", []):
        intent = edge.get("intent", "KEEP")
        if intent == "KEEP":
            continue
        source, target, relation = edge["source"], edge["target"], edge["relation"]
        if intent == "CREATE":
            depends = tuple(sorted(create_ops[end] for end in (source, target) if end in create_ops))
            operations.append(
                ChangeOperation(
                    id=f"connect:{source}->{target}:{relation}",
                    kind="CONNECT",
                    target_node=source,
                    locator=nodes.get(source, {}).get("locator"),
                    level=nodes.get(source, {}).get("level", "CODE"),
                    location=nodes.get(source, {}).get("location", "IN_REPOSITORY"),
                    depends_on=depends,
                    description=f"Connect {source} -{relation}-> {target}",
                )
            )
        elif intent == "REMOVE":
            operations.append(
                ChangeOperation(
                    id=f"disconnect:{source}->{target}:{relation}",
                    kind="DISCONNECT",
                    target_node=source,
                    locator=nodes.get(source, {}).get("locator"),
                    level=nodes.get(source, {}).get("level", "CODE"),
                    location=nodes.get(source, {}).get("location", "IN_REPOSITORY"),
                    depends_on=(),
                    description=f"Disconnect {source} -{relation}-> {target}",
                )
            )

    return ChangeSet(
        snapshot_id=str(snapshot.get("snapshot_id", "")),
        operations=tuple(sorted(operations, key=lambda op: op.id)),
        skipped=tuple(sorted(skipped, key=lambda item: item.target_node)),
        issues=tuple(sorted(issues, key=lambda item: item.target_node)),
    )


def _operation(prefix: str, kind: str, node: dict) -> ChangeOperation:
    return ChangeOperation(
        id=f"{prefix}:{node['id']}",
        kind=kind,
        target_node=node["id"],
        locator=node.get("locator"),
        level=node.get("level", "CODE"),
        location=node.get("location", "IN_REPOSITORY"),
        depends_on=(),
        description=node.get("description") or node.get("label", node["id"]),
    )


def changeset_to_json(changeset: ChangeSet) -> str:
    return json.dumps(
        {
            "snapshot_id": changeset.snapshot_id,
            "operations": [op.__dict__ | {"depends_on": list(op.depends_on)} for op in changeset.operations],
            "skipped": [item.__dict__ for item in changeset.skipped],
            "issues": [item.__dict__ for item in changeset.issues],
        },
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    )
