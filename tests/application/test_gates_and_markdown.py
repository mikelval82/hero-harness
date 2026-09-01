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
        store = MemoryArtifacts({"audit.md": audit, "task-contract.json": json.dumps(contract)})
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


if __name__ == "__main__":
    unittest.main()
