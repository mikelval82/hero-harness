import json

from src.harness.telemetry import (
    TELEMETRY_FILE,
    cost_record,
    format_cost_summary,
    parse_token_budget,
    read_events,
    summarize_costs,
    write_event,
    write_intervention,
    write_phase_event,
    write_task_event,
)


def test_cost_record_marks_price_as_missing_component():
    cost = cost_record(100, 25)

    assert cost["model"] is None
    assert cost["input_tokens"] == 100
    assert cost["output_tokens"] == 25
    assert cost["total_tokens"] == 125
    assert cost["estimated_usd"] is None
    assert cost["known"] is False
    assert cost["missing_component"] == "model_pricing"


def test_cost_record_estimates_known_model_price():
    cost = cost_record(1000, 500, model="claude-sonnet-4-6")

    assert cost["model"] == "claude-sonnet-4-6"
    assert cost["estimated_usd"] == 0.0105
    assert cost["known"] is True
    assert cost["missing_component"] is None


def test_write_event_appends_jsonl(tmp_path):
    write_event(tmp_path, "custom", task_id="T1")
    write_event(tmp_path, "custom", task_id="T2", ignored_none=None)

    events = read_events(tmp_path)
    assert [e["task_id"] for e in events] == ["T1", "T2"]
    assert "ignored_none" not in events[1]
    assert (tmp_path / TELEMETRY_FILE).is_file()


def test_write_phase_event_includes_cost(tmp_path):
    write_phase_event(
        tmp_path,
        "implement[T1]",
        result="success",
        turns=3,
        elapsed=12.34,
        input_tokens=1000,
        output_tokens=250,
        model="claude-haiku-4-5",
    )

    event = read_events(tmp_path)[0]
    assert event["event_type"] == "phase_result"
    assert event["phase"] == "implement[T1]"
    assert event["model"] == "claude-haiku-4-5"
    assert event["cost"]["total_tokens"] == 1250
    assert event["cost"]["estimated_usd"] == 0.00225
    assert event["cost"]["missing_component"] is None


def test_write_intervention_records_retry(tmp_path):
    write_intervention(
        tmp_path,
        "retry",
        task_id="T1",
        task_title="Fix parser",
        verdict="CHANGES_REQUESTED",
        feedback="cover empty input",
        retry_count=1,
    )

    event = read_events(tmp_path)[0]
    assert event["event_type"] == "intervention"
    assert event["action"] == "retry"
    assert event["source"] == "human"
    assert event["retry_count"] == 1


def test_write_task_event_records_missing_component(tmp_path):
    write_task_event(
        tmp_path,
        "task_failed",
        task_id="T1",
        task_title="Fix parser",
        status="failed",
        complexity="M",
        pipeline="spec -> plan -> implement -> review",
        complexity_reason="normal task",
        failure_reason="gate_fail",
        missing_component="phase_recovery",
    )

    raw = (tmp_path / TELEMETRY_FILE).read_text(encoding="utf-8").strip()
    event = json.loads(raw)
    assert event["event_type"] == "task_failed"
    assert event["failure_reason"] == "gate_fail"
    assert event["missing_component"] == "phase_recovery"


def test_summarize_costs_aggregates_phase_events(tmp_path):
    write_phase_event(tmp_path, "spec[1]", result="success", input_tokens=1000, output_tokens=250)
    write_phase_event(tmp_path, "plan[1]", result="success", input_tokens=2000, output_tokens=500)
    write_intervention(tmp_path, "retry", task_id="1", task_title="Task", retry_count=1)

    summary = summarize_costs(tmp_path, token_budget=4000)

    assert summary["phase_count"] == 2
    assert summary["input_tokens"] == 3000
    assert summary["output_tokens"] == 750
    assert summary["total_tokens"] == 3750
    assert summary["estimated_usd"] is None
    assert summary["known"] is False
    assert summary["missing_components"] == ["model_pricing"]
    assert summary["token_budget"] == 4000
    assert summary["remaining_tokens"] == 250
    assert summary["over_budget"] is False


def test_format_cost_summary_reports_unknown_pricing_and_budget_status(tmp_path):
    write_phase_event(tmp_path, "implement[1]", result="success", input_tokens=900, output_tokens=250)

    summary = format_cost_summary(tmp_path, token_budget=1000)

    assert summary.startswith("TOKEN/COST SUMMARY:")
    assert "total_tokens=1150" in summary
    assert "estimated_usd=unknown" in summary
    assert "token_budget=1000" in summary
    assert "remaining_tokens=-150" in summary
    assert "budget_status=over_budget" in summary
    assert "missing_components=model_pricing" in summary


def test_parse_token_budget_accepts_only_non_negative_integers():
    assert parse_token_budget("1000") == 1000
    assert parse_token_budget(" 0 ") == 0
    assert parse_token_budget("") is None
    assert parse_token_budget(None) is None
    assert parse_token_budget("-1") is None
    assert parse_token_budget("many") is None
