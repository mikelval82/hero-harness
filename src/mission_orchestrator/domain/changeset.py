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
    prepared_nodes: dict[str, dict] = {}
    resolving: set[str] = set()

    for original_node in nodes.values():
        node = _prepare_target_node(original_node, nodes, prepared_nodes, resolving)
        nodes[node["id"]] = node
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


_SOURCE_SUFFIXES = (
    "py", "pyi", "js", "jsx", "mjs", "cjs", "ts", "tsx", "java", "go",
    "rs", "rb", "php", "cs", "c", "h", "cc", "cpp", "hpp",
)


def _prepare_target_node(
    node: dict,
    nodes: dict[str, dict],
    prepared_nodes: dict[str, dict],
    resolving: set[str],
) -> dict:
    """Fill target metadata only when the design hierarchy makes it deterministic."""
    node_id = str(node.get("id", ""))
    if node_id in prepared_nodes:
        return prepared_nodes[node_id]
    if node_id in resolving:
        return node
    resolving.add(node_id)

    locator = node.get("locator") or _target_locator(node) or _locator_from_label(str(node.get("label", "")))
    if not locator:
        parent = nodes.get(str(node.get("parent_id", "")))
        if parent:
            parent = _prepare_target_node(parent, nodes, prepared_nodes, resolving)
            parent_locator = parent.get("locator") or _target_locator(parent)
            parent_path = _locator_path(parent_locator)
            if parent_path:
                node_kind = str(node.get("kind", "")).lower()
                label = str(node.get("label", ""))
                if node_kind == "module" or _source_filename(label):
                    filename = _source_filename(label)
                    if filename:
                        directory = parent_path.rsplit("/", 1)[0] if _is_source_path(parent_path) else parent_path
                        locator = "/".join(part for part in (directory, filename) if part)
                elif _is_source_path(parent_path):
                    symbol = str(node.get("qualified_name", "")).strip() or _identifier_from_label(label)
                    if symbol:
                        locator = f"{parent_path}:{symbol}"

    updates: dict[str, str] = {}
    if locator and not node.get("locator"):
        updates["locator"] = locator
    if locator and not node.get("target_path"):
        path = _locator_path(locator)
        if path:
            updates["target_path"] = path
    prepared = node | updates if updates else node
    prepared_nodes[node_id] = prepared
    resolving.discard(node_id)
    return prepared


def _locator_path(locator: object) -> str:
    value = str(locator or "").strip().replace("\\", "/")
    return value.split(":", 1)[0] if value else ""


def _is_source_path(path: str) -> bool:
    return path.lower().endswith(tuple(f".{suffix}" for suffix in _SOURCE_SUFFIXES))


def _source_filename(label: str) -> str | None:
    match = re.search(
        rf"(?<![\w/])([A-Za-z0-9_.-]+\.(?:{'|'.join(_SOURCE_SUFFIXES)}))(?:$|[\s)])",
        label,
        re.IGNORECASE,
    )
    return match.group(1) if match else None


def _identifier_from_label(label: str) -> str | None:
    match = re.search(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", label)
    return match.group(1) if match else None


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
