from __future__ import annotations

import sys
import json
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from mission_orchestrator.application.gate_evaluator import MarkdownGateEvaluator
from mission_orchestrator.application.markdown_contracts import (
    ReviewVerdict,
    audit_verdict,
    status_files,
)


class MemoryArtifacts:
    def __init__(self, files: dict[str, str]) -> None:
        self.files = files

    def exists(self, name: str) -> bool:
        return name in self.files

    def read_text(self, name: str, *, default: str | None = None) -> str:
        if name not in self.files:
            if default is not None:
                return default
            raise FileNotFoundError(name)
        return self.files[name]

    def write_text(self, name: str, content: str) -> None:
        self.files[name] = content

    def append_text(self, name: str, content: str) -> None:
        self.files[name] = self.files.get(name, "") + content

    def delete(self, name: str) -> None:
        self.files.pop(name, None)

    def path_for(self, name: str) -> Path:
        return Path(name)


class GatesAndMarkdownTest(unittest.TestCase):
    def test_gate_accepts_spanish_markers(self) -> None:
        store = MemoryArtifacts(
            {
                "brief.md": (
                    "# Brief\n\n## Objetivo\nAlgo\n\n## Decisiones\nUna\n\n"
                    "Notas\n**STATUS: DONE**\n"
                )
            }
        )
        result = MarkdownGateEvaluator(store).evaluate("grill", "brief.md")
        self.assertTrue(result.passed, result.detail)

    def test_gate_rejects_blocked_tail(self) -> None:
        store = MemoryArtifacts({"spec.md": "# S\n\n## Objective\nA\n\n## Expected Behavior\nB\n**STATUS: BLOCKED**\n"})
        result = MarkdownGateEvaluator(store).evaluate("spec", "spec.md")
        self.assertFalse(result.passed)

    def test_status_files_and_verdict(self) -> None:
        text = "## Files\n- `src/app.py`\n- tests/test_app.py\n\n## Other\n- ignore.md\n"
        self.assertEqual([path.as_posix() for path in status_files(text)], ["src/app.py", "tests/test_app.py"])
        self.assertEqual(audit_verdict("## Verdict\nMINOR_CHANGES\n"), ReviewVerdict.MINOR_CHANGES)

    def test_review_gate_requires_passing_terminal_validation_evidence(self) -> None:
        contract = {
            "validation_obligations": [
                {
                    "id": "VO:node:1",
                    "requirement_ids": ["ACC:node:1"],
                    "kind": "trusted_command",
                    "target": "src/example.py",
                    "expected": "imports",
                    "check_id": "target_validation",
                }
            ]
        }
        audit = "# Audit\n\n## Verdict\nAPPROVED\n\nNotes\n**STATUS: DONE**\n"
        review_evidence = {
            "schema_version": 1,
            "claims": [],
            "checks": [
                {"id": "hardcoding", "status": "pass", "evidence_refs": ["src/example.py:1"]},
                {"id": "special_casing", "status": "pass", "evidence_refs": ["src/example.py:1"]},
                {"id": "scope", "status": "pass", "evidence_refs": ["status.md"]},
            ],
            "failures": [],
        }
        store = MemoryArtifacts(
            {"audit.md": audit, "task-contract.json": json.dumps(contract), "review-evidence.json": json.dumps(review_evidence)}
        )
        missing = MarkdownGateEvaluator(store).evaluate("review", "audit.md")
        self.assertFalse(missing.passed)
        self.assertIn("NOT_RUN", missing.detail)

        store.files["validation-evidence/target_validation.json"] = json.dumps(
            {"check_id": "target_validation", "status": "fail"}
        )
        failed = MarkdownGateEvaluator(store).evaluate("review", "audit.md")
        self.assertFalse(failed.passed)
        self.assertIn("FAILED", failed.detail)

        store.files["validation-evidence/target_validation.json"] = json.dumps(
            {"check_id": "target_validation", "status": "pass"}
        )
        passed = MarkdownGateEvaluator(store).evaluate("review", "audit.md")
        self.assertTrue(passed.passed, passed.detail)

    def test_review_gate_rejects_approved_evaluation_check_that_did_not_run(self) -> None:
        audit = "# Audit\n\n## Verdict\nAPPROVED\n\nNotes\n**STATUS: DONE**\n"
        store = MemoryArtifacts(
            {
                "audit.md": audit,
                "review-evidence.json": json.dumps(
                    {
                        "schema_version": 1,
                        "claims": [],
                        "checks": [
                            {"id": "hardcoding", "status": "not_run", "evidence_refs": ["reason"]},
                            {"id": "special_casing", "status": "pass", "evidence_refs": ["src/a.py:1"]},
                            {"id": "scope", "status": "pass", "evidence_refs": ["status.md"]},
                        ],
                        "failures": [],
                    }
                ),
            }
        )
        result = MarkdownGateEvaluator(store).evaluate("review", "audit.md")
        self.assertFalse(result.passed)
        self.assertIn("NOT_RUN", result.detail)

    def test_review_gate_rejects_approved_unsupported_claim(self) -> None:
        audit = "# Audit\n\n## Verdict\nAPPROVED\n\nNotes\n**STATUS: DONE**\n"
        store = MemoryArtifacts(
            {
                "audit.md": audit,
                "review-evidence.json": json.dumps(
                    {
                        "schema_version": 1,
                        "claims": [
                            {
                                "id": "C1",
                                "statement": "The implementation is safe.",
                                "status": "unsupported",
                                "evidence_refs": ["src/a.py:1"],
                            }
                        ],
                        "checks": [
                            {"id": "hardcoding", "status": "pass", "evidence_refs": ["src/a.py:1"]},
                            {"id": "special_casing", "status": "pass", "evidence_refs": ["src/a.py:1"]},
                            {"id": "scope", "status": "pass", "evidence_refs": ["status.md"]},
                        ],
                        "failures": [],
                    }
                ),
            }
        )
        result = MarkdownGateEvaluator(store).evaluate("review", "audit.md")
        self.assertFalse(result.passed)
        self.assertIn("unsupported claims", result.detail)

    def test_review_gate_requires_taxonomy_for_non_approved_review(self) -> None:
        audit = "# Audit\n\n## Verdict\nMINOR_CHANGES\n\nNotes\n**STATUS: DONE**\n"
        evidence = {
            "schema_version": 1,
            "claims": [],
            "checks": [
                {"id": "hardcoding", "status": "pass", "evidence_refs": ["src/a.py:1"]},
                {"id": "special_casing", "status": "pass", "evidence_refs": ["src/a.py:1"]},
                {"id": "scope", "status": "pass", "evidence_refs": ["status.md"]},
            ],
            "failures": [],
        }
        store = MemoryArtifacts({"audit.md": audit, "review-evidence.json": json.dumps(evidence)})
        missing_taxonomy = MarkdownGateEvaluator(store).evaluate("review", "audit.md")
        self.assertFalse(missing_taxonomy.passed)
        self.assertIn("requires failure taxonomy", missing_taxonomy.detail)

        evidence["failures"] = [
            {
                "id": "F1",
                "failure_type": "technical_bug",
                "recoverability_lost_at_stage": "implement",
                "evidence_refs": ["src/a.py:1"],
            }
        ]
        store.files["review-evidence.json"] = json.dumps(evidence)
        self.assertTrue(MarkdownGateEvaluator(store).evaluate("review", "audit.md").passed)


if __name__ == "__main__":
    unittest.main()
