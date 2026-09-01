from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone


_SECRET = re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*[^\s,;]+")
_EXCLUDED = {
    "conversation", "messages", "_state.json", "_telemetry.jsonl",
    "token", "secret", "password", "api_key", "apikey",
}


@dataclass(frozen=True)
class MemoryEntry:
    key: str
    value: str
    provenance: str
    observed_at: str
    source_revision: str

    def to_json(self) -> dict[str, str]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class MemoryProposal:
    proposal_id: str
    key: str
    value: str
    base_hash: str
    created_at: str
    approved: bool = False

    def to_json(self) -> dict[str, object]:
        return self.__dict__.copy()


class ProjectMemory:
    """Read governed project memory; proposals are returned, never persisted."""

    def __init__(self, source) -> None:  # noqa: ANN001
        self.source = source

    def retrieve(self, key: str | None = None) -> list[MemoryEntry]:
        raw = self.source.read_text("PROJECT_MEMORY.json", default="[]")
        try:
            records = json.loads(raw)
        except (TypeError, ValueError):
            return []
        if not isinstance(records, list):
            return []
        result = []
        for record in records:
            if not isinstance(record, dict) or not isinstance(record.get("key"), str):
                continue
            item_key = record["key"]
            if key and item_key != key:
                continue
            if item_key.lower() in _EXCLUDED:
                continue
            value = _redact(str(record.get("value", "")))
            result.append(MemoryEntry(
                item_key,
                value,
                str(record.get("provenance", "unknown")),
                str(record.get("observed_at", "")),
                str(record.get("source_revision", "")),
            ))
        return result

    def propose(self, key: str, value: str) -> MemoryProposal:
        if not key.strip() or key.lower() in _EXCLUDED:
            raise ValueError("memory key is not eligible")
        safe_value = _redact(value)
        base = next((entry for entry in self.retrieve(key) if entry.key == key), None)
        base_hash = hashlib.sha256((base.value if base else "").encode()).hexdigest()
        now = datetime.now(timezone.utc).isoformat()
        proposal_id = hashlib.sha256(f"{key}\0{safe_value}\0{now}".encode()).hexdigest()[:16]
        return MemoryProposal(proposal_id, key, safe_value, base_hash, now)


def _redact(value: str) -> str:
    return _SECRET.sub(lambda match: match.group(1) + "=<redacted>", value)
