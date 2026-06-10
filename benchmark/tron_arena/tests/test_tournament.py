from __future__ import annotations

from benchmark.tron_arena.bots import (
    AlwaysLeftBot,
    RandomLegalBot,
    StraightUntilBlockedBot,
)
from benchmark.tron_arena.tournament import run_tournament


class TestRunTournament:
    def test_match_count_three_bots_two_seeds(self) -> None:
        bots = [
            ("always_left", AlwaysLeftBot),
            ("random_legal", RandomLegalBot),
            ("straight", StraightUntilBlockedBot),
        ]
        metrics, result = run_tournament(bots, seeds=[1, 2], width=5, height=5, max_turns=20)
        assert len(metrics) == 3 * 2 * 2  # N*(N-1)*S = 12

    def test_result_propagation(self) -> None:
        bots = [
            ("always_left", AlwaysLeftBot),
            ("random_legal", RandomLegalBot),
            ("straight", StraightUntilBlockedBot),
        ]
        metrics, result = run_tournament(bots, seeds=[1], width=5, height=5, max_turns=20)
        assert result.matches_played == len(metrics)
        for name, _ in bots:
            assert name in result.bot_names

    def test_empty_bots(self) -> None:
        metrics, result = run_tournament([], seeds=[1])
        assert metrics == []
        assert result.matches_played == 0

    def test_empty_seeds(self) -> None:
        bots = [("always_left", AlwaysLeftBot)]
        metrics, result = run_tournament(bots, seeds=[])
        assert metrics == []
        assert result.matches_played == 0

    def test_single_bot_zero_matches(self) -> None:
        bots = [("always_left", AlwaysLeftBot)]
        metrics, result = run_tournament(bots, seeds=[1], width=5, height=5, max_turns=20)
        assert len(metrics) == 0
        assert result.matches_played == 0

    def test_two_bots_one_seed(self) -> None:
        bots = [
            ("always_left", AlwaysLeftBot),
            ("random_legal", RandomLegalBot),
        ]
        metrics, result = run_tournament(bots, seeds=[42], width=5, height=5, max_turns=20)
        assert len(metrics) == 2  # 2*(2-1)*1 = 2
        assert result.matches_played == 2

    def test_metrics_have_replay_hashes(self) -> None:
        bots = [
            ("always_left", AlwaysLeftBot),
            ("random_legal", RandomLegalBot),
        ]
        metrics, _ = run_tournament(bots, seeds=[1], width=5, height=5, max_turns=20)
        for m in metrics:
            assert m.replay_hash is not None
            assert len(m.replay_hash) == 64
