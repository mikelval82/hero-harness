from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone


SCHEMA_VERSION = "l2-v1"
RETENTION_DAYS = 365


@dataclass(frozen=True)
class CaseRecord:
    case_id: str
    mission_tag: str
    task: str
    snapshot_id: str
    contract_id: str
    commit_sha: str
    receipt_ids: tuple[str, ...]
    score: float
    verified_at: str
    source_revision: str
    tombstoned: bool = False

    def to_json(self) -> dict[str, object]:
        return self.__dict__ | {"receipt_ids": list(self.receipt_ids), "schema_version": SCHEMA_VERSION}


class MissionCaseBase:
    """Read and validate anchored, terminal mission cases without auto-learning."""

    def __init__(self, source) -> None:  # noqa: ANN001
        self.source = source

    def retrieve(self, *, task: str | None = None) -> list[CaseRecord]:
        try:
            records = json.loads(self.source.read_text("CASE_BASE.json", default="[]"))
        except (TypeError, ValueError):
            return []
        if not isinstance(records, list):
            return []
        result = []
        for record in records:
            case = _parse(record)
            if case is None or case.tombstoned or (task and task.lower() not in case.task.lower()):
                continue
            result.append(case)
        return sorted(result, key=lambda item: (-item.score, item.verified_at))

    def revalidate(self, case: CaseRecord, *, current_revision: str) -> dict[str, object]:
        return {
            "case_id": case.case_id,
            "valid": bool(case.source_revision == current_revision and not case.tombstoned),
            "current_revision": current_revision,
            "case_revision": case.source_revision,
        }

    @staticmethod
    def tombstone(case_id: str, *, reason: str) -> dict[str, str]:
        if not case_id.strip() or not reason.strip():
            raise ValueError("case_id and reason are required")
        return {"case_id": case_id, "reason": reason, "tombstoned_at": datetime.now(timezone.utc).isoformat()}


def _parse(record: object) -> CaseRecord | None:
    if not isinstance(record, dict):
        return None
    required = ("case_id", "mission_tag", "task", "snapshot_id", "contract_id", "commit_sha", "receipt_ids", "score", "verified_at", "source_revision")
    if any(not record.get(key) for key in required) or record.get("status", "verified") != "verified":
        return None
    receipts = record.get("receipt_ids")
    if not isinstance(receipts, list) or not all(isinstance(item, str) for item in receipts):
        return None
    try:
        score = float(record["score"])
    except (TypeError, ValueError):
        return None
    return CaseRecord(
        case_id=str(record["case_id"]), mission_tag=str(record["mission_tag"]), task=str(record["task"]),
        snapshot_id=str(record["snapshot_id"]), contract_id=str(record["contract_id"]), commit_sha=str(record["commit_sha"]),
        receipt_ids=tuple(receipts), score=score, verified_at=str(record["verified_at"]), source_revision=str(record["source_revision"]),
        tombstoned=bool(record.get("tombstoned", False)),
    )
