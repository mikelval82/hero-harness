import json
from types import SimpleNamespace

from mission_orchestrator.application.case_base import MissionCaseBase


def test_case_base_keeps_only_anchored_verified_non_tombstoned_cases():
    source = SimpleNamespace(read_text=lambda name, default=None: json.dumps([
        {"case_id": "ok", "mission_tag": "m1", "task": "router", "snapshot_id": "s1", "contract_id": "c1", "commit_sha": "a" * 40, "receipt_ids": ["r1"], "score": 0.9, "verified_at": "2026-09-01", "source_revision": "rev1", "status": "verified"},
        {"case_id": "pending", "mission_tag": "m2", "task": "router", "snapshot_id": "s2", "contract_id": "c2", "commit_sha": "b" * 40, "receipt_ids": [], "score": 1, "verified_at": "2026-09-01", "source_revision": "rev1", "status": "pending"},
        {"case_id": "gone", "mission_tag": "m3", "task": "router", "snapshot_id": "s3", "contract_id": "c3", "commit_sha": "c" * 40, "receipt_ids": ["r3"], "score": 1, "verified_at": "2026-09-01", "source_revision": "rev1", "tombstoned": True},
    ]))
    base = MissionCaseBase(source)
    cases = base.retrieve(task="route")
    assert [case.case_id for case in cases] == ["ok"]
    assert base.revalidate(cases[0], current_revision="rev2")["valid"] is False


def test_case_tombstone_requires_reason():
    try:
        MissionCaseBase.tombstone("", reason="")
    except ValueError:
        pass
    else:
        raise AssertionError("invalid tombstone accepted")
