"""Offline/shadow-only evaluation for the experimental O8 review strategy."""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median


@dataclass(frozen=True)
class ReviewObservation:
    case_id: str
    mode: str
    tokens: int
    turns: int
    findings: frozenset[str]
    blocking_findings: frozenset[str]
    downstream_rework: bool = False


@dataclass(frozen=True)
class ReviewMetrics:
    cases: int
    median_tokens: float
    p90_tokens: float
    median_turns: float
    p90_turns: float
    blocking_findings_omitted: int
    downstream_rework: int
    non_inferior: bool

    def to_json(self) -> dict[str, object]:
        return self.__dict__.copy()


class ProgressiveReviewExperiment:
    """Compare progressive review against a frozen full-review baseline.

    This class never activates or changes runtime review behavior. It only
    produces auditable metrics from paired shadow observations.
    """

    def evaluate(
        self,
        baseline: list[ReviewObservation],
        progressive: list[ReviewObservation],
    ) -> ReviewMetrics:
        if not baseline:
            raise ValueError("baseline corpus must not be empty")
        baseline_by_id = {item.case_id: item for item in baseline}
        progressive_by_id = {item.case_id: item for item in progressive}
        if set(baseline_by_id) != set(progressive_by_id):
            raise ValueError("baseline and progressive corpora must contain the same case ids")
        omitted = sum(
            len(base.blocking_findings - progressive_by_id[case_id].findings)
            for case_id, base in baseline_by_id.items()
        )
        rework = sum(item.downstream_rework for item in progressive)
        tokens = [item.tokens for item in progressive]
        turns = [item.turns for item in progressive]
        baseline_tokens = sum(item.tokens for item in baseline)
        baseline_omitted = 0
        non_inferior = omitted == baseline_omitted and rework == 0 and sum(tokens) <= baseline_tokens
        return ReviewMetrics(
            cases=len(baseline),
            median_tokens=median(tokens),
            p90_tokens=_p90(tokens),
            median_turns=median(turns),
            p90_turns=_p90(turns),
            blocking_findings_omitted=omitted,
            downstream_rework=rework,
            non_inferior=non_inferior,
        )


def _p90(values: list[int]) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * 0.9)))
    return float(ordered[index])
