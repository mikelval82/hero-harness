from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from mission_orchestrator.adapters.tools.registry import default_tool_registry
from mission_orchestrator.application.phase_registry import PHASES
from mission_orchestrator.domain.phase import PhaseAuthority, PhaseName
from mission_orchestrator.ports.tool_registry import ToolAuthorizationError, ToolEnvironment


class RecordingLogger:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.metrics: list[dict] = []

    def log(self, message: str) -> None:
        del message

    def tool_call(self, name: str, input: dict) -> None:
        self.calls.append((name, input))

    def metric(self, record: dict) -> None:
        self.metrics.append(record)


class PhaseAuthorityTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.project = root / "project"
        self.harness = root / "harness"
        self.project.mkdir()
        self.harness.mkdir()
        self.env = ToolEnvironment(self.project, self.harness)
        self.logger = RecordingLogger()
        self.registry = default_tool_registry(self.logger)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_r1_matrix_declares_exact_project_and_harness_authority(self) -> None:
        expected_harness_writes = {
            PhaseName.RESEARCH: ("brainstorm.md",),
            PhaseName.STRUCTURE: ("tasks.json",),
            PhaseName.GRILL: ("brief.md",),
            PhaseName.SPEC: ("spec.md",),
            PhaseName.PLAN: ("plan.md", "decisions.md"),
            PhaseName.IMPLEMENT: ("status.md",),
            PhaseName.IMPLEMENT_BURSTS: ("_burst_progress.md", "status.md"),
            PhaseName.REVIEW: ("audit.md", "review-evidence.json"),
            PhaseName.REIMPLEMENT: ("status.md",),
            PhaseName.COMPACT: ("_compact_tmp.md",),
            PhaseName.CONSOLIDATE: ("tasks.json",),
            PhaseName.REPORT: ("mission-report.md",),
            PhaseName.REPORT_PLAN: ("mission-report.md",),
        }
        project_writers = {
            PhaseName.IMPLEMENT,
            PhaseName.IMPLEMENT_BURSTS,
            PhaseName.REIMPLEMENT,
        }

        self.assertEqual(set(PHASES), set(expected_harness_writes))
        for phase, expected_paths in expected_harness_writes.items():
            authority = PHASES[phase].authority
            self.assertEqual(authority.harness_write_paths, expected_paths)
            self.assertEqual(authority.allow_project_writes, phase in project_writers)
            self.assertEqual("Bash" in authority.tools, phase in project_writers)
        for phase in (PhaseName.RESEARCH, PhaseName.GRILL):
            self.assertEqual(PHASES[phase].authority.harness_mutation_tools, ("GraphPropose",))

    def test_schemas_are_derived_from_the_same_authority(self) -> None:
        research = self.registry.schemas_for(PHASES[PhaseName.RESEARCH].authority)
        review = self.registry.schemas_for(PHASES[PhaseName.REVIEW].authority)

        self.assertEqual(
            {schema["name"] for schema in research},
            {"Read", "Glob", "Grep", "Write", "CodeGraph", "GraphQuery", "GraphPropose"},
        )
        self.assertEqual(
            {schema["name"] for schema in review},
            {"Read", "Glob", "Grep", "Write", "WriteJson", "RunValidation"},
        )

    def test_non_implementing_phase_cannot_write_the_project_and_emits_safe_telemetry(self) -> None:
        secret_path = self.project / "secret.py"
        with self.assertRaises(ToolAuthorizationError) as raised:
            self.registry.execute(
                "Write",
                {"file_path": str(secret_path), "content": "secret-value"},
                self.env,
                PHASES[PhaseName.REVIEW].authority,
            )

        self.assertEqual(raised.exception.reason, "project_write_not_allowed")
        self.assertFalse(secret_path.exists())
        self.assertEqual(
            self.logger.metrics[-1],
            {
                "event": "tool_rejected",
                "phase": "review",
                "tool": "Write",
                "reason": "project_write_not_allowed",
            },
        )
        self.assertNotIn("secret-value", repr(self.logger.metrics[-1]))

    def test_each_phase_can_only_write_its_declared_harness_artifacts(self) -> None:
        authority = PHASES[PhaseName.SPEC].authority
        allowed = self.harness / "spec.md"
        self.registry.execute(
            "Write",
            {"file_path": str(allowed), "content": "# Spec\n"},
            self.env,
            authority,
        )
        self.assertEqual(allowed.read_text(encoding="utf-8"), "# Spec\n")

        blocked = self.harness / "audit.md"
        with self.assertRaises(ToolAuthorizationError) as raised:
            self.registry.execute(
                "Write",
                {"file_path": str(blocked), "content": "not permitted"},
                self.env,
                authority,
            )
        self.assertEqual(raised.exception.reason, "harness_artifact_not_allowed")
        self.assertFalse(blocked.exists())

    def test_implementation_can_write_project_but_spec_cannot_invoke_unannounced_graph_mutation(self) -> None:
        project_file = self.project / "src" / "service.py"
        self.registry.execute(
            "Write",
            {"file_path": str(project_file), "content": "class Service: pass\n"},
            self.env,
            PHASES[PhaseName.IMPLEMENT].authority,
        )
        self.assertTrue(project_file.exists())

        with self.assertRaises(ToolAuthorizationError) as raised:
            self.registry.execute(
                "GraphPropose",
                {"operation_id": "bypass", "base_revision": 0, "operations": []},
                self.env,
                PHASES[PhaseName.SPEC].authority,
            )
        self.assertEqual(raised.exception.reason, "tool_not_allowed")
        self.assertFalse((self.harness / "design.db").exists())

    def test_missing_authority_denies_instead_of_defaulting_to_access(self) -> None:
        with self.assertRaises(ToolAuthorizationError) as raised:
            self.registry.execute("Read", {"file_path": "missing.txt"}, self.env, None)
        self.assertEqual(raised.exception.reason, "missing_authority")
        self.assertEqual(self.logger.metrics[-1]["phase"], "")

    def test_unregistered_tool_in_a_phase_definition_fails_closed(self) -> None:
        authority = PhaseAuthority(PhaseName.RESEARCH, ("NotRegistered",))
        with self.assertRaises(ToolAuthorizationError) as raised:
            self.registry.schemas_for(authority)
        self.assertEqual(raised.exception.reason, "tool_unregistered")
        self.assertEqual(self.logger.metrics[-1]["tool"], "NotRegistered")

    def test_review_can_request_only_the_fixed_validation_check(self) -> None:
        with self.assertRaises(ToolAuthorizationError) as raised:
            self.registry.execute(
                "RunValidation",
                {"check_id": "target_validation"},
                self.env,
                PHASES[PhaseName.RESEARCH].authority,
            )
        self.assertEqual(raised.exception.reason, "tool_not_allowed")
        self.assertEqual(
            self.registry.execute(
                "RunValidation",
                {"check_id": "target_validation"},
                self.env,
                PHASES[PhaseName.REVIEW].authority,
            ),
            "exit=not_configured\nNo mission validation script is configured.",
        )


if __name__ == "__main__":
    unittest.main()
