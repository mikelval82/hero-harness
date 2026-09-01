from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone


MIN_CORPUS = 2


@dataclass(frozen=True)
class RefinementProposal:
    proposal_id: str
    pattern: str
    case_ids: tuple[str, ...]
    occurrences: int
    rationale: str
    created_at: str
    approval_required: bool = True
    auto_apply: bool = False

    def to_json(self) -> dict[str, object]:
        return self.__dict__ | {"case_ids": list(self.case_ids)}


class MissionRefiner:
    """Derive explainable, proposal-only hints from verified case findings."""

    def propose(self, cases: list[dict[str, object]]) -> list[RefinementProposal]:
        if len(cases) < MIN_CORPUS:
            return []
        occurrences: defaultdict[str, set[str]] = defaultdict(set)
        for case in cases:
            case_id = str(case.get("case_id", ""))
            findings = case.get("findings", [])
            if not case_id or not isinstance(findings, list):
                continue
            for finding in findings:
                pattern = str(finding).strip().lower()
                if pattern:
                    occurrences[pattern].add(case_id)
        result = []
        for pattern, case_ids in sorted(occurrences.items()):
            if len(case_ids) < MIN_CORPUS:
                continue
            ordered = tuple(sorted(case_ids))
            proposal_id = hashlib.sha256(f"{pattern}:{','.join(ordered)}".encode()).hexdigest()[:16]
            result.append(RefinementProposal(
                proposal_id, pattern, ordered, len(ordered),
                "Recurring observation; investigate as a hypothesis, not a causal claim.",
                datetime.now(timezone.utc).isoformat(),
            ))
        return result
