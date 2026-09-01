from __future__ import annotations

import json
from typing import Any

from mission_orchestrator.domain.validation import ValidationKind, ValidationObligation


def compile_validation_obligations(nodes: list[dict[str, Any]]) -> list[dict[str, object]]:
    """Create stable, blocking validation obligations from approved acceptance criteria."""
    obligations: list[ValidationObligation] = []
    for node in sorted(nodes, key=lambda item: str(item.get("id", ""))):
        node_id = str(node.get("id", "")).strip()
        target = str(node.get("target_path") or node.get("locator") or node_id).strip()
        requirements = [str(item).strip() for item in node.get("satisfies", []) if str(item).strip()]
        for index, expected in enumerate(node.get("acceptance", []) or [], start=1):
            expected_text = str(expected).strip()
            if not expected_text:
                continue
            acceptance_id = f"ACC:{node_id}:{index}"
            obligations.append(
                ValidationObligation(
                    id=f"VO:{node_id}:{index}",
                    requirement_ids=tuple(sorted(set([*requirements, acceptance_id]))),
                    kind=ValidationKind.TRUSTED_COMMAND,
                    target=target,
                    expected=expected_text,
                    check_id="target_validation",
                )
            )
    return [obligation.to_json() for obligation in obligations]


def read_validation_obligations(contract_text: str) -> list[ValidationObligation]:
    if not contract_text:
        return []
    try:
        payload = json.loads(contract_text)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid task contract JSON") from exc
    raw_obligations = payload.get("validation_obligations", [])
    if not isinstance(raw_obligations, list):
        raise ValueError("validation_obligations must be a list")
    return [ValidationObligation.from_json(item) for item in raw_obligations]
