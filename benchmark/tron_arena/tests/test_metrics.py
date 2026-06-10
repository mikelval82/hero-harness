from __future__ import annotations

from benchmark.tron_arena.actions import Action
from benchmark.tron_arena.engine import MatchResult
from benchmark.tron_arena.metrics import (
    MatchMetrics,
    TournamentResult,
    aggregate_results,
    match_metrics_from_result,
)


class TestMatchMetricsFromResult:
    def test_maps_all_fields(self) -> None:
        result = MatchResult(
            winner=0,
            turns=10,
            end_reason="collision",
            action_history=[{0: Action.STRAIGHT, 1: Action.STRAIGHT}],
            invalid_counts={0: 1, 1: 0},
            crash_counts={0: 0, 1: 2},
        )
        metrics = match_metrics_from_result(
            result, seed=42, bot_names={0: "A", 1: "B"}, replay_hash="abc123"
        )
        assert metrics.seed == 42
        assert metrics.bot_names == {0: "A", 1: "B"}
        assert metrics.winner == 0
        assert metrics.turns == 10
        assert metrics.end_reason == "collision"
        assert metrics.invalid_counts == {0: 1, 1: 0}
        assert metrics.crash_counts == {0: 0, 1: 2}
        assert metrics.timeout_counts == {0: 0, 1: 0}
        assert metrics.replay_hash == "abc123"

    def test_timeout_counts_default_to_zero(self) -> None:
        result = MatchResult(
            winner=None,
            turns=5,
            end_reason="draw",
            action_history=[],
            invalid_counts={0: 0, 1: 0},
            crash_counts={0: 0, 1: 0},
        )
        metrics = match_metrics_from_result(
            result, seed=1, bot_names={0: "X", 1: "Y"}
        )
        assert metrics.timeout_counts == {0: 0, 1: 0}
        assert metrics.replay_hash is None

    def test_to_dict_converts_int_keys_to_string(self) -> None:
        metrics = MatchMetrics(
            seed=1,
            bot_names={0: "A", 1: "B"},
            winner=0,
            turns=5,
            end_reason="collision",
            invalid_counts={0: 1, 1: 0},
            crash_counts={0: 0, 1: 0},
            timeout_counts={0: 0, 1: 0},
            replay_hash=None,
        )
        d = metrics.to_dict()
        assert d["bot_names"] == {"0": "A", "1": "B"}
        assert d["invalid_counts"] == {"0": 1, "1": 0}
        assert d["crash_counts"] == {"0": 0, "1": 0}
        assert d["timeout_counts"] == {"0": 0, "1": 0}


class TestAggregateResults:
    def test_winner_scenario(self) -> None:
        m1 = MatchMetrics(
            seed=1, bot_names={0: "A", 1: "B"}, winner=0, turns=10,
            end_reason="collision", invalid_counts={0: 0, 1: 0},
            crash_counts={0: 0, 1: 0}, timeout_counts={0: 0, 1: 0},
            replay_hash=None,
        )
        m2 = MatchMetrics(
            seed=1, bot_names={0: "B", 1: "A"}, winner=0, turns=8,
            end_reason="collision", invalid_counts={0: 0, 1: 0},
            crash_counts={0: 0, 1: 0}, timeout_counts={0: 0, 1: 0},
            replay_hash=None,
        )
        result = aggregate_results([m1, m2])
        assert result.wins == {"A": 1, "B": 1}
        assert result.losses == {"A": 1, "B": 1}
        assert result.draws["A"] == 0
        assert result.draws["B"] == 0
        assert result.win_rates == {"A": 0.5, "B": 0.5}
        assert result.matches_played == 2

    def test_draw_scenario(self) -> None:
        m = MatchMetrics(
            seed=1, bot_names={0: "A", 1: "B"}, winner=None, turns=200,
            end_reason="max_turns", invalid_counts={0: 0, 1: 0},
            crash_counts={0: 0, 1: 0}, timeout_counts={0: 0, 1: 0},
            replay_hash=None,
        )
        result = aggregate_results([m])
        assert result.draws == {"A": 1, "B": 1}
        assert result.wins.get("A", 0) == 0
        assert result.wins.get("B", 0) == 0
        assert result.losses.get("A", 0) == 0
        assert result.losses.get("B", 0) == 0
        assert result.win_rates == {"A": 0.0, "B": 0.0}

    def test_self_play(self) -> None:
        m = MatchMetrics(
            seed=1, bot_names={0: "A", 1: "A"}, winner=0, turns=10,
            end_reason="collision", invalid_counts={0: 0, 1: 0},
            crash_counts={0: 0, 1: 0}, timeout_counts={0: 0, 1: 0},
            replay_hash=None,
        )
        result = aggregate_results([m])
        assert result.wins == {"A": 1}
        assert result.losses == {"A": 1}
        assert result.win_rates["A"] == 0.5

    def test_empty_list(self) -> None:
        result = aggregate_results([])
        assert result.matches_played == 0
        assert result.bot_names == []
        assert result.wins == {}
        assert result.losses == {}
        assert result.draws == {}
        assert result.win_rates == {}
        assert result.avg_survival_turns == {}
        assert result.illegal_counts == {}
        assert result.crash_counts == {}
        assert result.timeout_counts == {}

    def test_avg_survival_turns(self) -> None:
        m1 = MatchMetrics(
            seed=1, bot_names={0: "A", 1: "B"}, winner=0, turns=10,
            end_reason="collision", invalid_counts={0: 0, 1: 0},
            crash_counts={0: 0, 1: 0}, timeout_counts={0: 0, 1: 0},
            replay_hash=None,
        )
        m2 = MatchMetrics(
            seed=2, bot_names={0: "A", 1: "B"}, winner=0, turns=20,
            end_reason="collision", invalid_counts={0: 0, 1: 0},
            crash_counts={0: 0, 1: 0}, timeout_counts={0: 0, 1: 0},
            replay_hash=None,
        )
        result = aggregate_results([m1, m2])
        assert result.avg_survival_turns["A"] == 15.0
        assert result.avg_survival_turns["B"] == 15.0

    def test_illegal_and_crash_accumulation(self) -> None:
        m = MatchMetrics(
            seed=1, bot_names={0: "A", 1: "B"}, winner=0, turns=10,
            end_reason="collision", invalid_counts={0: 3, 1: 1},
            crash_counts={0: 0, 1: 2}, timeout_counts={0: 1, 1: 0},
            replay_hash=None,
        )
        result = aggregate_results([m])
        assert result.illegal_counts == {"A": 3, "B": 1}
        assert result.crash_counts == {"A": 0, "B": 2}
        assert result.timeout_counts == {"A": 1, "B": 0}
