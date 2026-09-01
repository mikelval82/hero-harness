from mission_orchestrator.application.progressive_review import (
    ProgressiveReviewExperiment,
    ReviewObservation,
)


def _case(case_id, findings, blocking, *, tokens=100, rework=False):
    return ReviewObservation(case_id, "full", tokens, 2, frozenset(findings), frozenset(blocking), rework)


def test_shadow_review_reports_percentiles_and_non_inferiority():
    baseline = [_case("api", {"api"}, {"api"}, tokens=100), _case("schema", {"schema"}, {"schema"}, tokens=120)]
    progressive = [_case("api", {"api"}, {"api"}, tokens=80), _case("schema", {"schema"}, {"schema"}, tokens=100)]
    metrics = ProgressiveReviewExperiment().evaluate(baseline, progressive)
    assert metrics.cases == 2
    assert metrics.median_tokens == 90
    assert metrics.p90_tokens == 80
    assert metrics.blocking_findings_omitted == 0
    assert metrics.non_inferior is True


def test_shadow_review_blocks_omissions_rework_and_misaligned_corpus():
    baseline = [_case("scope", {"scope"}, {"scope"})]
    progressive = [_case("scope", set(), {"scope"}, rework=True)]
    metrics = ProgressiveReviewExperiment().evaluate(baseline, progressive)
    assert metrics.blocking_findings_omitted == 1
    assert metrics.downstream_rework == 1
    assert metrics.non_inferior is False
    try:
        ProgressiveReviewExperiment().evaluate(baseline, [_case("other", set(), set())])
    except ValueError:
        pass
    else:
        raise AssertionError("misaligned corpus was accepted")
