from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone


SCHEMA_VERSION = "l3-v1"
ALLOWED_STATUSES = {"candidate", "approved", "revoked"}


@dataclass(frozen=True)
class SkillRecord:
    skill_id: str
    version: str
    summary: str
    content: str
    permissions: tuple[str, ...]
    receipt_ids: tuple[str, ...]
    status: str
    created_at: str
    content_trusted: bool = False

    def to_json(self) -> dict[str, object]:
        return self.__dict__ | {
            "permissions": list(self.permissions),
            "receipt_ids": list(self.receipt_ids),
            "schema_version": SCHEMA_VERSION,
        }


class SkillLibrary:
    """Versioned skill index; retrieved content is data, never system authority."""

    def __init__(self, source) -> None:  # noqa: ANN001
        self.source = source

    def retrieve(self, skill_id: str | None = None) -> list[SkillRecord]:
        try:
            records = json.loads(self.source.read_text("SKILL_LIBRARY.json", default="[]"))
        except (TypeError, ValueError):
            return []
        if not isinstance(records, list):
            return []
        result = []
        for record in records:
            skill = _parse(record)
            if skill and skill.status != "revoked" and (skill_id is None or skill.skill_id == skill_id):
                result.append(skill)
        return sorted(result, key=lambda item: (item.skill_id, item.version))

    @staticmethod
    def promotion_proposal(skill: SkillRecord, *, human_approved: bool = False) -> dict[str, object]:
        if skill.status == "revoked":
            raise ValueError("revoked skill cannot be promoted")
        return {
            "proposal_id": hashlib.sha256(f"{skill.skill_id}@{skill.version}".encode()).hexdigest()[:16],
            "skill_id": skill.skill_id,
            "version": skill.version,
            "permissions": list(skill.permissions),
            "receipt_ids": list(skill.receipt_ids),
            "human_approved": human_approved,
            "apply": False,
        }


def _parse(record: object) -> SkillRecord | None:
    if not isinstance(record, dict):
        return None
    required = ("skill_id", "version", "summary", "content", "permissions", "receipt_ids", "created_at")
    if any(not record.get(key) for key in required):
        return None
    status = str(record.get("status", "candidate"))
    if status not in ALLOWED_STATUSES or not isinstance(record["permissions"], list) or not isinstance(record["receipt_ids"], list):
        return None
    return SkillRecord(
        str(record["skill_id"]), str(record["version"]), str(record["summary"]), str(record["content"]),
        tuple(str(item) for item in record["permissions"]), tuple(str(item) for item in record["receipt_ids"]),
        status, str(record["created_at"]), False,
    )
