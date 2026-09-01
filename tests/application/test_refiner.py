from mission_orchestrator.application.refiner import MissionRefiner


def test_refiner_requires_corpus_and_returns_explainable_proposals_only():
    refiner = MissionRefiner()
    assert refiner.propose([{"case_id": "a", "findings": ["schema"]}]) == []
    proposals = refiner.propose([
        {"case_id": "a", "findings": ["schema", "scope"]},
        {"case_id": "b", "findings": ["schema"]},
    ])
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.pattern == "schema"
    assert proposal.case_ids == ("a", "b")
    assert proposal.approval_required is True
    assert proposal.auto_apply is False


def test_refiner_does_not_claim_causality_or_emit_mutations():
    proposal = MissionRefiner().propose([
        {"case_id": "a", "findings": ["api"]},
        {"case_id": "b", "findings": ["api"]},
    ])[0]
    assert "causal" in proposal.rationale
    assert not hasattr(proposal, "apply")
