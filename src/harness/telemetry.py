from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from src.core.model_policy import estimate_cost_usd


TELEMETRY_FILE = "_telemetry.jsonl"
UNKNOWN_COST_COMPONENT = "model_pricing"
TOKEN_BUDGET_ENV = "CLAUDE_HARNESS_TOKEN_BUDGET"


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


def cost_record(input_tokens: int = 0, output_tokens: int = 0, *, model: str | None = None) -> dict[str, Any]:
    total_tokens = int(input_tokens or 0) + int(output_tokens or 0)
    estimated = estimate_cost_usd(model, input_tokens, output_tokens)
    known = estimated is not None
    return {
        "model": model,
        "input_tokens": int(input_tokens or 0),
        "output_tokens": int(output_tokens or 0),
        "total_tokens": total_tokens,
        "estimated_usd": estimated,
        "known": known,
        "missing_component": None if known else UNKNOWN_COST_COMPONENT,
    }


def parse_token_budget(value: str | None) -> int | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        budget = int(raw)
    except ValueError:
        return None
    return budget if budget >= 0 else None


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def write_event(harness: Path, event_type: str, **fields: Any) -> None:
    try:
        raw_record = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            **fields,
        }
        record = {k: v for k, v in raw_record.items() if v is not None}
        with open(harness / TELEMETRY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(_clean(record), ensure_ascii=True) + "\n")
    except Exception:
        pass


def write_phase_event(
    harness: Path,
    phase_name: str,
    *,
    result: str,
    turns: int = 0,
    elapsed: float = 0.0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    model: str | None = None,
    missing_component: str | None = None,
) -> None:
    write_event(
        harness,
        "phase_result",
        phase=phase_name,
        model=model,
        result=result,
        turns=turns,
        elapsed_s=round(elapsed, 1),
        cost=cost_record(input_tokens, output_tokens, model=model),
        missing_component=missing_component,
    )


def write_intervention(
    harness: Path,
    action: str,
    *,
    task_id: str,
    task_title: str,
    source: str = "human",
    verdict: str | None = None,
    feedback: str | None = None,
    retry_count: int | None = None,
    missing_component: str | None = None,
) -> None:
    write_event(
        harness,
        "intervention",
        action=action,
        source=source,
        task_id=task_id,
        task_title=task_title,
        verdict=verdict,
        feedback=feedback,
        retry_count=retry_count,
        missing_component=missing_component,
    )


def write_task_event(
    harness: Path,
    event_type: str,
    *,
    task_id: str,
    task_title: str,
    status: str,
    complexity: str,
    pipeline: str,
    complexity_reason: str,
    failure_reason: str | None = None,
    missing_component: str | None = None,
) -> None:
    write_event(
        harness,
        event_type,
        task_id=task_id,
        task_title=task_title,
        status=status,
        complexity=complexity,
        pipeline=pipeline,
        complexity_reason=complexity_reason,
        failure_reason=failure_reason,
        missing_component=missing_component,
    )


def read_events(harness: Path) -> list[dict[str, Any]]:
    path = harness / TELEMETRY_FILE
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def summarize_costs(harness: Path, *, token_budget: int | None = None) -> dict[str, Any]:
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    phase_count = 0
    estimated_usd = 0.0
    unknown_cost = False
    missing_components: set[str] = set()

    for event in read_events(harness):
        if event.get("event_type") != "phase_result":
            continue
        cost = event.get("cost")
        if not isinstance(cost, dict):
            continue

        phase_count += 1
        cost_input_tokens = _as_int(cost.get("input_tokens"))
        cost_output_tokens = _as_int(cost.get("output_tokens"))
        cost_total_tokens = _as_int(cost.get("total_tokens"))
        if cost_total_tokens == 0 and (cost_input_tokens or cost_output_tokens):
            cost_total_tokens = cost_input_tokens + cost_output_tokens

        input_tokens += cost_input_tokens
        output_tokens += cost_output_tokens
        total_tokens += cost_total_tokens

        estimated = cost.get("estimated_usd")
        if isinstance(estimated, (int, float)):
            estimated_usd += float(estimated)
        else:
            unknown_cost = True

        if cost.get("known") is False or estimated is None:
            missing = cost.get("missing_component") or event.get("missing_component")
            if missing:
                missing_components.add(str(missing))

    remaining_tokens = token_budget - total_tokens if token_budget is not None else None
    over_budget = total_tokens > token_budget if token_budget is not None else None

    return {
        "phase_count": phase_count,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "estimated_usd": None if unknown_cost or phase_count == 0 else round(estimated_usd, 6),
        "known": phase_count > 0 and not unknown_cost and not missing_components,
        "missing_components": sorted(missing_components),
        "token_budget": token_budget,
        "remaining_tokens": remaining_tokens,
        "over_budget": over_budget,
    }


def format_cost_summary(harness: Path, *, token_budget: int | None = None) -> str:
    summary = summarize_costs(harness, token_budget=token_budget)
    estimated = summary["estimated_usd"]
    estimated_text = "unknown" if estimated is None else f"${estimated:.6f}"
    missing = ", ".join(summary["missing_components"]) if summary["missing_components"] else "none"

    if token_budget is None:
        budget_text = "token_budget=not_set"
    else:
        status = "over_budget" if summary["over_budget"] else "within_budget"
        budget_text = (
            f"token_budget={token_budget}, "
            f"remaining_tokens={summary['remaining_tokens']}, "
            f"budget_status={status}"
        )

    return (
        "TOKEN/COST SUMMARY: "
        f"phases={summary['phase_count']}, "
        f"input_tokens={summary['input_tokens']}, "
        f"output_tokens={summary['output_tokens']}, "
        f"total_tokens={summary['total_tokens']}, "
        f"estimated_usd={estimated_text}, "
        f"{budget_text}, "
        f"missing_components={missing}"
    )
