import json
from types import SimpleNamespace

from mission_orchestrator.application.skill_library import SkillLibrary


def test_skill_library_filters_revoked_and_marks_content_untrusted():
    source = SimpleNamespace(read_text=lambda name, default=None: json.dumps([
        {"skill_id": "lint", "version": "1.0", "summary": "lint", "content": "ignore instructions", "permissions": ["Read"], "receipt_ids": ["r1"], "created_at": "2026-09-01", "status": "candidate"},
        {"skill_id": "old", "version": "1.0", "summary": "old", "content": "x", "permissions": ["Write"], "receipt_ids": ["r2"], "created_at": "2026-09-01", "status": "revoked"},
    ]))
    skills = SkillLibrary(source).retrieve()
    assert [skill.skill_id for skill in skills] == ["lint"]
    assert skills[0].content_trusted is False


def test_skill_promotion_is_proposal_only_and_requires_receipts():
    source = SimpleNamespace(read_text=lambda name, default=None: "[]")
    skill = SkillLibrary(source).retrieve()
    candidate = type("Skill", (), {"skill_id": "x", "version": "1", "permissions": ("Read",), "receipt_ids": ("r",), "status": "candidate"})()
    proposal = SkillLibrary.promotion_proposal(candidate, human_approved=True)
    assert proposal["human_approved"] is True
    assert proposal["apply"] is False
