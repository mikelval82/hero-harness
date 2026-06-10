from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.harness.case_base import HARNESS_CASES_PATH_FILE, read_cases
from src.harness.telemetry import read_events


REFINER_PROPOSAL_FILE = "refiner-proposal.md"
REFINER_MIN_RECURRENCE = 2

FAILURE_TYPES = {
    "technical_bug",
    "spec_mismatch",
    "semantic_mismatch",
    "evaluation_hacking",
    "unclear_requirement",
    "over_scoping",
    "missing_test",
    "context_loss",
}

_FAILURE_TYPE_RE = re.compile(r"failure_type:\s*([a-zA-Z_]+)", re.IGNORECASE)
_STAGE_RE = re.compile(r"recoverability_lost_at_stage:\s*([a-zA-Z_]+)", re.IGNORECASE)


@dataclass(frozen=True)
class FailureSignal:
    failure_type: str
    stage: str
    source: str
    evidence: str

    @property
    def signature(self) -> str:
        return f"{self.failure_type}@{self.stage}"


def _read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _excerpt(text: str, max_chars: int = 220) -> str:
    compact = " ".join(line.strip() for line in text.splitlines() if line.strip())
    if len(compact) <= max_chars:
        return compact
    return compact[:max_chars].rstrip() + "..."


def _normalize_failure_type(value: str) -> str:
    normalized = value.strip().lower()
    return normalized if normalized in FAILURE_TYPES else "unknown"


def _normalize_stage(value: str) -> str:
    stage = value.strip().lower()
    return stage or "unknown"


def _infer_failure_type(text: str) -> str:
    lowered = text.lower()
    for failure_type in FAILURE_TYPES:
        if failure_type in lowered:
            return failure_type
    if "test" in lowered or "validation" in lowered:
        return "missing_test"
    if "semantic" in lowered or "intent" in lowered:
        return "semantic_mismatch"
    if "context" in lowered or "drift" in lowered:
        return "context_loss"
    if "scope" in lowered:
        return "over_scoping"
    if "requirement" in lowered or "unclear" in lowered:
        return "unclear_requirement"
    return "unknown"


def extract_failure_signals_from_text(text: str, *, source: str) -> list[FailureSignal]:
    signals = []
    for match in _FAILURE_TYPE_RE.finditer(text):
        failure_type = _normalize_failure_type(match.group(1))
        if failure_type in {"none", "unknown"}:
            continue
        window = text[match.start(): match.start() + 600]
        stage_match = _STAGE_RE.search(window)
        stage = _normalize_stage(stage_match.group(1)) if stage_match else "unknown"
        signals.append(FailureSignal(
            failure_type=failure_type,
            stage=stage,
            source=source,
            evidence=_excerpt(window),
        ))
    return signals


def _signals_from_telemetry(harness: Path) -> list[FailureSignal]:
    signals = []
    for event in read_events(harness):
        event_type = event.get("event_type")
        if event_type == "task_failed":
            reason = str(event.get("failure_reason") or event.get("status") or "task failed")
            signals.append(FailureSignal(
                failure_type=_infer_failure_type(reason),
                stage="implement",
                source="_telemetry.jsonl",
                evidence=_excerpt(reason),
            ))
        elif event_type == "intervention" and event.get("action") in {"reject", "retry", "auto_reimplement"}:
            feedback = str(event.get("feedback") or event.get("verdict") or event.get("action"))
            signals.append(FailureSignal(
                failure_type=_infer_failure_type(feedback),
                stage="review",
                source="_telemetry.jsonl",
                evidence=_excerpt(feedback),
            ))
    return [signal for signal in signals if signal.failure_type != "unknown"]


def _signals_from_case_base(harness: Path) -> list[FailureSignal]:
    pointer = harness / HARNESS_CASES_PATH_FILE
    if not pointer.is_file():
        return []
    raw_cases_path = pointer.read_text(encoding="utf-8").strip()
    if not raw_cases_path:
        return []

    signals = []
    for case in read_cases(Path(raw_cases_path)):
        case_id = str(case.get("case_id") or "case")
        chunks = [
            str(case.get("audit_summary") or ""),
            str(case.get("report_summary") or ""),
            " ".join(str(item) for item in case.get("lessons") or []),
        ]
        signals.extend(extract_failure_signals_from_text(
            "\n".join(chunks),
            source=f"cases.jsonl:{case_id}",
        ))
    return signals


def collect_failure_signals(harness: Path) -> list[FailureSignal]:
    signals = []
    for artifact in ("audit.md", "status.md", "mission-report.md"):
        signals.extend(extract_failure_signals_from_text(
            _read_text(harness / artifact),
            source=artifact,
        ))
    signals.extend(_signals_from_telemetry(harness))
    signals.extend(_signals_from_case_base(harness))
    return signals


def _group_signals(signals: list[FailureSignal]) -> dict[str, list[FailureSignal]]:
    grouped: dict[str, list[FailureSignal]] = defaultdict(list)
    for signal in signals:
        grouped[signal.signature].append(signal)
    return dict(grouped)


def _suggestion_for(failure_type: str, stage: str) -> dict[str, Any]:
    if failure_type == "missing_test":
        return {
            "title": "Strengthen deterministic check coverage",
            "target_artifacts": ["prompts/spec-prompt.md", "prompts/review-prompt.md"],
            "change_type": "prompt_contract",
            "proposal": (
                "Require the specifier to add a cheap deterministic check for the "
                "recurring missed behavior, and require the reviewer to mark approval "
                "blocked when that check is absent or not run without alternative evidence."
            ),
        }
    if failure_type == "semantic_mismatch":
        return {
            "title": "Tighten semantic alignment before planning",
            "target_artifacts": ["agents/griller.md", "prompts/grill-prompt.md", "prompts/spec-prompt.md"],
            "change_type": "alignment_contract",
            "proposal": (
                "Add a targeted clarification step for the recurring mismatch and require "
                "the spec to cite user intent evidence before creating acceptance criteria."
            ),
        }
    if failure_type == "context_loss":
        return {
            "title": "Reinforce context carryover at retry boundary",
            "target_artifacts": ["prompts/reimplement-prompt.md", "prompts/implement-burst-prompt.md"],
            "change_type": "regrounding_contract",
            "proposal": (
                "Make the retry or burst prompt restate the lost fact as a required "
                "constraint and ask the implementer to cite it in Self-Verification."
            ),
        }
    if failure_type == "evaluation_hacking":
        return {
            "title": "Harden evaluation hacking audit",
            "target_artifacts": ["agents/reviewer.md", "prompts/review-prompt.md"],
            "change_type": "review_contract",
            "proposal": (
                "Add a concrete negative check for the recurring hack pattern and require "
                "file:line evidence before approval."
            ),
        }
    if failure_type == "over_scoping":
        return {
            "title": "Constrain implementation scope",
            "target_artifacts": ["agents/planner.md", "agents/implementer.md", "prompts/plan-prompt.md"],
            "change_type": "scope_contract",
            "proposal": (
                "Require non-goals to be copied into plan and status for this recurring "
                "scope boundary, and require reviewer evidence when scope expands."
            ),
        }
    if failure_type == "unclear_requirement":
        return {
            "title": "Promote unclear requirement to grill/spec decision",
            "target_artifacts": ["prompts/grill-prompt.md", "prompts/spec-prompt.md"],
            "change_type": "clarification_contract",
            "proposal": (
                "Add a pre-spec clarification checkpoint for this recurring ambiguity and "
                "block plan generation until a decision or explicit assumption is recorded."
            ),
        }
    return {
        "title": "Investigate recurring failure signature",
        "target_artifacts": ["agents/reviewer.md", "prompts/review-prompt.md"],
        "change_type": "investigation",
        "proposal": (
            "Add a narrow diagnostic question or audit field only after a human confirms "
            "the signature is causal and not incidental."
        ),
    }


def build_refiner_proposal(
    harness: Path,
    *,
    min_recurrence: int = REFINER_MIN_RECURRENCE,
) -> str:
    signals = collect_failure_signals(harness)
    grouped = _group_signals(signals)
    counts = Counter(signal.signature for signal in signals)
    recurrent = [
        (signature, grouped[signature])
        for signature, count in counts.most_common()
        if count >= min_recurrence
    ]
    candidates = [
        (signature, grouped[signature])
        for signature, count in counts.most_common()
        if count < min_recurrence
    ]

    sections = [
        "---",
        "status: proposed",
        "approval_required: true",
        "auto_apply: false",
        "generated_by: offline_refiner",
        f"min_recurrence: {min_recurrence}",
        "---",
        "# Refiner Proposal",
        "",
        "This proposal is advisory. It must not be applied automatically.",
        "A human must review the evidence, edit the proposed change, and apply it manually.",
        "",
        "## Evidence Reviewed",
        f"- failure_signals: {len(signals)}",
        f"- recurrent_signatures: {len(recurrent)}",
        f"- proposal_file_only: {REFINER_PROPOSAL_FILE}",
        "",
    ]

    if not signals:
        sections.extend([
            "## Recurrent Failure Signatures",
            "- none found",
            "",
            "## Proposed Harness Changes",
            "- none",
            "",
            "## Human Approval",
            "- decision: no_change",
            "- reason: no failure evidence was found.",
            "",
            "## Non-Application Guarantee",
            "- This process only writes `refiner-proposal.md`.",
            "- It does not edit prompts, agents, code, tests, memory, cases, or skills.",
        ])
        return "\n".join(sections).rstrip() + "\n"

    sections.extend(["## Recurrent Failure Signatures"])
    if recurrent:
        for signature, signature_signals in recurrent:
            sections.append(f"- {signature}: {len(signature_signals)} signals")
            for signal in signature_signals[:3]:
                sections.append(f"  - {signal.source}: {signal.evidence or 'no excerpt'}")
    else:
        sections.append(f"- none reached threshold `{min_recurrence}`")
    sections.append("")

    if candidates:
        sections.append("## Non-Recurrent Candidate Signals")
        for signature, signature_signals in candidates[:8]:
            sections.append(f"- {signature}: {len(signature_signals)} signal(s)")
        sections.append("")

    sections.append("## Proposed Harness Changes")
    if not recurrent:
        sections.extend([
            "- none",
            "",
            "Reason: no failure signature is recurrent enough to justify changing prompts or agents.",
        ])
    else:
        for idx, (signature, signature_signals) in enumerate(recurrent, start=1):
            failure_type, stage = signature.split("@", 1)
            suggestion = _suggestion_for(failure_type, stage)
            sections.extend([
                f"### RP{idx}: {suggestion['title']}",
                f"- failure_signature: {signature}",
                f"- observed_count: {len(signature_signals)}",
                f"- change_type: {suggestion['change_type']}",
                "- target_artifacts:",
            ])
            for target in suggestion["target_artifacts"]:
                sections.append(f"  - {target}")
            sections.extend([
                f"- proposed_change: {suggestion['proposal']}",
                "- expected_value: reduce recurrence of this exact failure signature.",
                "- risk: prompt overfitting if the signature is incidental or too sparse.",
                "- approval_required: true",
                "- auto_apply: false",
                "",
            ])

    sections.extend([
        "## Human Approval",
        "- Review whether each signature is causal, repeated, and worth changing the harness for.",
        "- If approved, create a normal implementation task and update prompts/agents with tests.",
        "- If rejected, leave this proposal as historical evidence and make no harness changes.",
        "",
        "## Non-Application Guarantee",
        "- This process only writes `refiner-proposal.md`.",
        "- It does not edit prompts, agents, code, tests, memory, cases, or skills.",
    ])
    return "\n".join(sections).rstrip() + "\n"


def write_refiner_proposal(
    harness: Path,
    *,
    min_recurrence: int = REFINER_MIN_RECURRENCE,
) -> Path:
    harness.mkdir(parents=True, exist_ok=True)
    proposal = build_refiner_proposal(harness, min_recurrence=min_recurrence)
    path = harness / REFINER_PROPOSAL_FILE
    path.write_text(proposal, encoding="utf-8")
    return path
