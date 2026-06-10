from __future__ import annotations

import dataclasses
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional

from benchmark.tron_arena.engine import MatchResult


@dataclass
class MatchMetrics:
    seed: int
    bot_names: Dict[int, str]
    winner: Optional[int]
    turns: int
    end_reason: str
    invalid_counts: Dict[int, int]
    crash_counts: Dict[int, int]
    timeout_counts: Dict[int, int]
    replay_hash: Optional[str]

    def to_dict(self) -> dict:
        return {
            "seed": self.seed,
            "bot_names": {str(k): v for k, v in self.bot_names.items()},
            "winner": self.winner,
            "turns": self.turns,
            "end_reason": self.end_reason,
            "invalid_counts": {str(k): v for k, v in self.invalid_counts.items()},
            "crash_counts": {str(k): v for k, v in self.crash_counts.items()},
            "timeout_counts": {str(k): v for k, v in self.timeout_counts.items()},
            "replay_hash": self.replay_hash,
        }


@dataclass
class TournamentResult:
    bot_names: List[str]
    matches_played: int
    wins: Dict[str, int]
    losses: Dict[str, int]
    draws: Dict[str, int]
    win_rates: Dict[str, float]
    avg_survival_turns: Dict[str, float]
    illegal_counts: Dict[str, int]
    crash_counts: Dict[str, int]
    timeout_counts: Dict[str, int]

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def match_metrics_from_result(
    result: MatchResult,
    seed: int,
    bot_names: Dict[int, str],
    replay_hash: Optional[str] = None,
) -> MatchMetrics:
    return MatchMetrics(
        seed=seed,
        bot_names=bot_names,
        winner=result.winner,
        turns=result.turns,
        end_reason=result.end_reason,
        invalid_counts=result.invalid_counts,
        crash_counts=result.crash_counts,
        timeout_counts={pid: 0 for pid in bot_names},
        replay_hash=replay_hash,
    )


def aggregate_results(matches: List[MatchMetrics]) -> TournamentResult:
    if not matches:
        return TournamentResult(
            bot_names=[],
            matches_played=0,
            wins={},
            losses={},
            draws={},
            win_rates={},
            avg_survival_turns={},
            illegal_counts={},
            crash_counts={},
            timeout_counts={},
        )

    wins: Dict[str, int] = defaultdict(int)
    losses: Dict[str, int] = defaultdict(int)
    draws: Dict[str, int] = defaultdict(int)
    illegal: Dict[str, int] = defaultdict(int)
    crash: Dict[str, int] = defaultdict(int)
    timeout: Dict[str, int] = defaultdict(int)
    survival_total: Dict[str, int] = defaultdict(int)
    match_count: Dict[str, int] = defaultdict(int)

    for match in matches:
        for pid, name in match.bot_names.items():
            match_count[name] += 1
            survival_total[name] += match.turns
            illegal[name] += match.invalid_counts.get(pid, 0)
            crash[name] += match.crash_counts.get(pid, 0)
            timeout[name] += match.timeout_counts.get(pid, 0)

            if match.winner is None:
                draws[name] += 1
            elif match.winner == pid:
                wins[name] += 1
            else:
                losses[name] += 1

    all_names = sorted(set(match_count.keys()))

    win_rates: Dict[str, float] = {}
    avg_survival: Dict[str, float] = {}
    for name in all_names:
        total = wins[name] + losses[name] + draws[name]
        win_rates[name] = wins[name] / total if total > 0 else 0.0
        count = match_count[name]
        avg_survival[name] = survival_total[name] / count if count > 0 else 0.0

    return TournamentResult(
        bot_names=all_names,
        matches_played=len(matches),
        wins=dict(wins),
        losses=dict(losses),
        draws=dict(draws),
        win_rates=win_rates,
        avg_survival_turns=avg_survival,
        illegal_counts=dict(illegal),
        crash_counts=dict(crash),
        timeout_counts=dict(timeout),
    )
