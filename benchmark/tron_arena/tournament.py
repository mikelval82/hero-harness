from __future__ import annotations

from typing import List, Tuple

from benchmark.tron_arena.engine import GameConfig, run_match
from benchmark.tron_arena.metrics import (
    MatchMetrics,
    TournamentResult,
    aggregate_results,
    match_metrics_from_result,
)
from benchmark.tron_arena.replay import replay_from_match, replay_hash


def run_tournament(
    bots: List[Tuple[str, type]],
    seeds: List[int],
    width: int = 20,
    height: int = 20,
    max_turns: int = 200,
) -> Tuple[List[MatchMetrics], TournamentResult]:
    if not bots or not seeds:
        return [], aggregate_results([])

    all_metrics: List[MatchMetrics] = []

    for seed in seeds:
        config = GameConfig(seed=seed, width=width, height=height, max_turns=max_turns)
        for i, (name_a, cls_a) in enumerate(bots):
            for j, (name_b, cls_b) in enumerate(bots):
                if i == j:
                    continue
                result = run_match(config, cls_a, cls_b)
                bot_names = {0: name_a, 1: name_b}
                replay = replay_from_match(config, result, bot_names)
                hash_val = replay_hash(replay)
                metrics = match_metrics_from_result(result, seed, bot_names, replay_hash=hash_val)
                all_metrics.append(metrics)

    tournament_result = aggregate_results(all_metrics)
    return all_metrics, tournament_result
