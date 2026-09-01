import json
from types import SimpleNamespace

from mission_orchestrator.application.project_memory import ProjectMemory


class _Source:
    def __init__(self, value):
        self.value = value
    def read_text(self, name, *, default=None):
        assert name == "PROJECT_MEMORY.json"
        return self.value


def test_memory_retrieval_has_provenance_redaction_and_exclusions():
    source = _Source(json.dumps([
        {"key": "lint", "value": "Use ruff", "provenance": "receipt:R1", "observed_at": "2026-09-01", "source_revision": "abc"},
        {"key": "token", "value": "api_key=SECRET", "provenance": "bad"},
        {"key": "_state.json", "value": "transient"},
    ]))
    entries = ProjectMemory(source).retrieve()
    assert len(entries) == 1
    assert entries[0].provenance == "receipt:R1"


def test_memory_proposal_is_redacted_and_does_not_write():
    source = _Source("[]")
    proposal = ProjectMemory(source).propose("convention", "token=SECRET")
    assert "SECRET" not in proposal.value
    assert proposal.approved is False
