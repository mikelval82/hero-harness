from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from mission_orchestrator.application.markdown_contracts import ReviewVerdict, audit_verdict


REQUIRED_CHECKS = frozenset({"hardcoding", "special_casing", "scope"})
CHECK_STATUSES = frozenset({"pass", "fail", "not_run"})
FAILURE_TYPES = frozenset({"technical_bug", "spec_mismatch", "semantic_mismatch", "evaluation_hacking", "unclear_requirement", "over_scoping", "missing_test", "context_loss"})
RECOVERY_STAGES = frozenset({"research", "grill", "spec", "plan", "implement", "implement_bursts", "review", "reimplement", "user_input", "unknown"})


@dataclass(frozen=True)
class ReviewEvidence:
    claims: tuple[dict[str, Any], ...]
    checks: tuple[dict[str, Any], ...]
    failures: tuple[dict[str, Any], ...]

    @classmethod
    def from_json(cls, text: str) -> "ReviewEvidence":
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("review evidence is not valid JSON") from exc
        if not isinstance(value, dict) or value.get("schema_version") != 1:
            raise ValueError("review evidence schema_version must be 1")
        claims = _objects(value.get("claims"), "claims")
        checks = _objects(value.get("checks"), "checks")
        failures = _objects(value.get("failures"), "failures")
        _validate_claims(claims)
        _validate_checks(checks)
        _validate_failures(failures)
        return cls(tuple(claims), tuple(checks), tuple(failures))

    def gate_error(self, audit_text: str) -> str:
        verdict = audit_verdict(audit_text)
        if verdict == ReviewVerdict.UNKNOWN:
            return "review evidence requires a known audit verdict"
        if verdict == ReviewVerdict.APPROVED:
            if any(claim["status"] != "supported" for claim in self.claims):
                return "APPROVED review has unsupported claims"
            if any(check["status"] != "pass" for check in self.checks):
                return "APPROVED review has failed or NOT_RUN review checks"
            if self.failures:
                return "APPROVED review cannot retain failure taxonomy entries"
        elif not self.failures:
            return "non-approved review requires failure taxonomy entries"
        return ""

    def to_json(self) -> dict[str, object]:
        return {"schema_version": 1, "claims": list(self.claims), "checks": list(self.checks), "failures": list(self.failures)}


def _objects(value: object, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"review evidence {field} must be a list of objects")
    return value


def _references(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"review evidence {field} requires non-empty evidence_refs")
    return [item.strip() for item in value]


def _validate_claims(claims: list[dict[str, Any]]) -> None:
    for claim in claims:
        if not str(claim.get("id", "")).strip() or not str(claim.get("statement", "")).strip():
            raise ValueError("review evidence claim requires id and statement")
        if claim.get("status") not in {"supported", "unsupported"}:
            raise ValueError("review evidence claim has invalid status")
        _references(claim.get("evidence_refs"), "claim")


def _validate_checks(checks: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    for check in checks:
        check_id = str(check.get("id", "")).strip()
        if check_id not in REQUIRED_CHECKS or check_id in seen:
            raise ValueError("review evidence checks must contain hardcoding, special_casing, and scope once")
        seen.add(check_id)
        if check.get("status") not in CHECK_STATUSES:
            raise ValueError("review evidence check has invalid status")
        _references(check.get("evidence_refs"), "check")
    if seen != REQUIRED_CHECKS:
        raise ValueError("review evidence is missing required review checks")


def _validate_failures(failures: list[dict[str, Any]]) -> None:
    for failure in failures:
        if not str(failure.get("id", "")).strip():
            raise ValueError("review evidence failure requires id (for example F1)")
        if failure.get("failure_type") not in FAILURE_TYPES:
            allowed = ", ".join(sorted(FAILURE_TYPES))
            raise ValueError(f"review evidence failure has invalid failure_type; allowed: {allowed}")
        if failure.get("recoverability_lost_at_stage") not in RECOVERY_STAGES:
            allowed = ", ".join(sorted(RECOVERY_STAGES))
            raise ValueError(
                "review evidence failure has invalid recoverability_lost_at_stage; "
                f"allowed: {allowed}"
            )
        _references(failure.get("evidence_refs"), "failure")
