from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import PurePosixPath


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
    node_kind: str = "unknown"
    target_path: str = ""
    qualified_name: str = ""
    signature: str = ""
    docstring: str = ""
    satisfies: tuple[str, ...] = ()
    acceptance: tuple[str, ...] = ()
    source: str | None = None
    target: str | None = None
    relation: str | None = None
    verification_level: str = "advisory"


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
        locator = node.get("locator") or _target_locator(node)
        if intent == "CREATE" and not locator:
            locator = _locator_from_label(node.get("label", ""))
            if locator:
                node = node | {"locator": locator}
        elif locator and not node.get("locator"):
            node = node | {"locator": locator}
        resolved = bool(locator) and locator in observed_ids
        if intent == "KEEP":
            continue
        if intent == "CREATE":
            if resolved:
                skipped.append(SkippedChange(node["id"], "already_materialized"))
                continue
            if _requires_repository_target(node) and not locator:
                issues.append(
                    ChangeIssue(
                        node["id"],
                        "CREATE requires a valid target_path or deterministically derivable locator",
                    )
                )
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
                    source=source,
                    target=target,
                    relation=relation,
                    verification_level=_relationship_verification(edge),
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
                    source=source,
                    target=target,
                    relation=relation,
                    verification_level=_relationship_verification(edge),
                )
            )

    return ChangeSet(
        snapshot_id=str(snapshot.get("snapshot_id", "")),
        operations=tuple(sorted(operations, key=lambda op: op.id)),
        skipped=tuple(sorted(skipped, key=lambda item: item.target_node)),
        issues=tuple(sorted(issues, key=lambda item: item.target_node)),
    )


def _locator_from_label(label: str) -> str | None:
    # CP-4: a path-like label is the expected observed id of the artifact to create.
    if re.fullmatch(r"[\w.\-]+(/[\w.\-]+)+(:[\w.]+)?", label):
        return label
    return None


def _target_locator(node: dict) -> str | None:
    target_path = str(node.get("target_path", "")).strip().replace("\\", "/")
    if not _valid_target_path(target_path):
        return None
    qualified_name = str(node.get("qualified_name", "")).strip()
    return f"{target_path}:{qualified_name}" if qualified_name else target_path


def _valid_target_path(target_path: str) -> bool:
    if not target_path or target_path.startswith("/") or re.match(r"^[A-Za-z]:", target_path):
        return False
    path = PurePosixPath(target_path)
    return all(part not in {"", ".", ".."} for part in path.parts)


def _requires_repository_target(node: dict) -> bool:
    return node.get("location", "IN_REPOSITORY") == "IN_REPOSITORY" and node.get(
        "level", "CODE"
    ) in {"CODE", "PACKAGE"}


def _relationship_verification(edge: dict) -> str:
    relation = str(edge.get("relation", "")).lower()
    if relation in {"contains", "inherits"}:
        return "hard"
    if relation == "imports" and edge.get("provenance") == "ANALYZER":
        return "resolved"
    return "advisory"


def _operation(prefix: str, kind: str, node: dict) -> ChangeOperation:
    locator = node.get("locator") or _target_locator(node)
    return ChangeOperation(
        id=f"{prefix}:{node['id']}",
        kind=kind,
        target_node=node["id"],
        locator=locator,
        level=node.get("level", "CODE"),
        location=node.get("location", "IN_REPOSITORY"),
        depends_on=(),
        description=node.get("description") or node.get("label", node["id"]),
        node_kind=str(node.get("kind", "unknown")),
        target_path=str(node.get("target_path", "")),
        qualified_name=str(node.get("qualified_name", "")),
        signature=str(node.get("signature", "")),
        docstring=str(node.get("docstring", "")),
        satisfies=tuple(str(item) for item in node.get("satisfies", [])),
        acceptance=tuple(str(item) for item in node.get("acceptance", [])),
        verification_level=(
            "hard" if node.get("location", "IN_REPOSITORY") == "IN_REPOSITORY" else "advisory"
        ),
    )


def changeset_to_json(changeset: ChangeSet) -> str:
    return json.dumps(
        {
            "snapshot_id": changeset.snapshot_id,
            "operations": [
                op.__dict__
                | {
                    "depends_on": list(op.depends_on),
                    "satisfies": list(op.satisfies),
                    "acceptance": list(op.acceptance),
                }
                for op in changeset.operations
            ],
            "skipped": [item.__dict__ for item in changeset.skipped],
            "issues": [item.__dict__ for item in changeset.issues],
        },
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    )
