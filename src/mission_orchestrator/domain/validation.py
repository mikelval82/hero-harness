from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ValidationKind(Enum):
    TRUSTED_COMMAND = "trusted_command"
    STATIC = "static"
    BROWSER = "browser"
    MANUAL = "manual"


class ValidationStatus(Enum):
    PASS = "pass"
    FAIL = "fail"
    NOT_RUN = "not_run"


@dataclass(frozen=True)
class ValidationObligation:
    """An immutable validation requirement attached to a task contract."""

    id: str
    requirement_ids: tuple[str, ...]
    kind: ValidationKind
    target: str
    expected: str
    check_id: str | None = None
    provenance: str = "task_contract"

    def to_json(self) -> dict[str, object]:
        return {
            "id": self.id,
            "requirement_ids": list(self.requirement_ids),
            "kind": self.kind.value,
            "target": self.target,
            "expected": self.expected,
            "check_id": self.check_id,
            "provenance": self.provenance,
        }

    @classmethod
    def from_json(cls, value: dict[str, Any]) -> "ValidationObligation":
        try:
            kind = ValidationKind(str(value["kind"]))
            obligation_id = str(value["id"]).strip()
            requirement_ids = tuple(str(item).strip() for item in value["requirement_ids"])
            target = str(value["target"]).strip()
            expected = str(value["expected"]).strip()
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid validation obligation") from exc
        if not obligation_id or not requirement_ids or not target or not expected:
            raise ValueError("validation obligation has empty required fields")
        check_id = value.get("check_id")
        if kind is ValidationKind.TRUSTED_COMMAND and not isinstance(check_id, str):
            raise ValueError("trusted command obligation requires check_id")
        return cls(
            id=obligation_id,
            requirement_ids=requirement_ids,
            kind=kind,
            target=target,
            expected=expected,
            check_id=str(check_id).strip() if check_id else None,
            provenance=str(value.get("provenance", "task_contract")),
        )


@dataclass(frozen=True)
class ValidationEvidence:
    obligation_id: str
    status: ValidationStatus
    actor: str
    observed_at: str
    document_ref: str
    detail: str

    def to_json(self) -> dict[str, str]:
        return {
            "obligation_id": self.obligation_id,
            "status": self.status.value,
            "actor": self.actor,
            "observed_at": self.observed_at,
            "document_ref": self.document_ref,
            "detail": self.detail,
        }
