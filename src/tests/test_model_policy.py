from src.core.model_policy import (
    CHEAP_MODEL,
    DEFAULT_MODEL,
    DEEP_MODEL,
    MODEL_CHEAP_ENV,
    MODEL_DEFAULT_ENV,
    MODEL_DEEP_ENV,
    MODEL_FORCE_ENV,
    estimate_cost_usd,
    normalize_phase_name,
    resolve_model_id,
    select_model_for_phase,
)


def test_normalize_phase_name_strips_task_and_burst_suffix():
    assert normalize_phase_name("implement[T1]#2") == "implement"
    assert normalize_phase_name("compact[researcher]") == "compact"
    assert normalize_phase_name("report") == "report"


def test_resolve_model_id_defaults(monkeypatch):
    monkeypatch.delenv(MODEL_FORCE_ENV, raising=False)
    monkeypatch.delenv(MODEL_CHEAP_ENV, raising=False)
    monkeypatch.delenv(MODEL_DEFAULT_ENV, raising=False)
    monkeypatch.delenv(MODEL_DEEP_ENV, raising=False)

    assert resolve_model_id("cheap") == CHEAP_MODEL
    assert resolve_model_id("default") == DEFAULT_MODEL
    assert resolve_model_id("deep") == DEEP_MODEL
    assert resolve_model_id("unknown") == DEFAULT_MODEL


def test_resolve_model_id_respects_overrides(monkeypatch):
    monkeypatch.setenv(MODEL_CHEAP_ENV, "cheap-override")
    monkeypatch.setenv(MODEL_DEFAULT_ENV, "default-override")
    monkeypatch.setenv(MODEL_DEEP_ENV, "deep-override")

    assert resolve_model_id("cheap") == "cheap-override"
    assert resolve_model_id("default") == "default-override"
    assert resolve_model_id("deep") == "deep-override"


def test_force_override_wins(monkeypatch):
    monkeypatch.setenv(MODEL_FORCE_ENV, "forced-model")
    monkeypatch.setenv(MODEL_DEEP_ENV, "deep-override")

    selection = select_model_for_phase("review", task_complexity="L")

    assert selection.tier == "forced"
    assert selection.model == "forced-model"
    assert resolve_model_id("cheap") == "forced-model"


def test_select_model_for_phase_routes_by_phase_and_complexity(monkeypatch):
    monkeypatch.delenv(MODEL_FORCE_ENV, raising=False)

    assert select_model_for_phase("compact[T1]").tier == "cheap"
    assert select_model_for_phase("report_plan").tier == "cheap"
    assert select_model_for_phase("grill").tier == "deep"
    assert select_model_for_phase("review").tier == "deep"
    assert select_model_for_phase("implement[T1]", task_complexity="L").tier == "deep"
    assert select_model_for_phase("implement[T1]", task_complexity="M").tier == "default"
    assert select_model_for_phase("research", mode="explore").tier == "deep"
    assert select_model_for_phase("research", mode="full").tier == "default"


def test_estimate_cost_usd_for_known_model():
    assert estimate_cost_usd("claude-haiku-4-5", input_tokens=1_000_000, output_tokens=1_000_000) == 6.0
    assert estimate_cost_usd("claude-sonnet-4-6", input_tokens=1000, output_tokens=500) == 0.0105
    assert estimate_cost_usd("unknown-model", input_tokens=1000, output_tokens=500) is None
