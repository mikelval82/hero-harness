from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from mission_orchestrator.application.pipeline_definitions import mission_pipeline_for, mode_should_merge, task_pipeline_for
from mission_orchestrator.domain.block import BlockKind, BlockReason
from mission_orchestrator.domain.command import CommandKind, parse_control_command
from mission_orchestrator.domain.mission import GateMode, MissionMode
from mission_orchestrator.domain.phase import PhaseName
from mission_orchestrator.domain.task import Task, TaskComplexity, TaskStatus, summarize_tasks


class DomainContractsTest(unittest.TestCase):
    def test_pipeline_selection(self) -> None:
        full = mission_pipeline_for(MissionMode.FULL, no_grill=False)
        self.assertEqual(
            full.init,
            (PhaseName.RESEARCH, PhaseName.COMPACT, PhaseName.GRILL, PhaseName.STRUCTURE),
        )
        self.assertEqual(
            task_pipeline_for(Task("T-1", "large", TaskComplexity.L), MissionMode.FULL).phases,
            (PhaseName.SPEC, PhaseName.PLAN, PhaseName.IMPLEMENT_BURSTS, PhaseName.REVIEW),
        )
        self.assertEqual(
            task_pipeline_for(Task("T-2", "small", TaskComplexity.S), MissionMode.PLAN).phases,
            (PhaseName.SPEC, PhaseName.PLAN),
        )
        self.assertEqual(
            task_pipeline_for(Task("T-3", "small", TaskComplexity.S), MissionMode.FULL).phases,
            (PhaseName.SPEC, PhaseName.PLAN, PhaseName.IMPLEMENT),
        )

    def test_spec_only_is_non_mutating_and_alias_has_plan_pipeline(self) -> None:
        spec = mission_pipeline_for(MissionMode.SPEC, no_grill=False)
        self.assertEqual(spec.init, ())
        self.assertEqual(spec.finalize, (PhaseName.SPEC, PhaseName.REPORT_PLAN))
        self.assertFalse(spec.task_loop)
        self.assertFalse(mode_should_merge(MissionMode.SPEC))
        self.assertEqual(
            mission_pipeline_for(MissionMode.PLAN, no_grill=False).init,
            mission_pipeline_for(MissionMode.parse("spec-plan"), no_grill=False).init,
        )

    def test_block_reason_and_commands(self) -> None:
        block = BlockReason(BlockKind.GATE_FAIL, "spec", "missing marker")
        self.assertEqual(str(block), "gate_fail | phase=spec | missing marker")
        self.assertFalse(block.is_mission_abort)
        command = parse_control_command("/gate on")
        self.assertIsNotNone(command)
        self.assertEqual(command.kind, CommandKind.GATE)
        self.assertEqual(command.gate_mode, GateMode.MANUAL)
        answer = parse_control_command("plain human answer")
        self.assertEqual(answer.kind, CommandKind.ANSWER)
        self.assertEqual(answer.text, "plain human answer")

    def test_task_summary(self) -> None:
        tasks = [
            Task("T-1", "done", status=TaskStatus.COMPLETED),
            Task("T-2", "bad", status=TaskStatus.FAILED, failure_reason="nope"),
            Task("T-3", "todo"),
        ]
        self.assertEqual(
            summarize_tasks(tasks),
            "Total: 3 | Completed: 1 | Failed: 1 | Blocked: 0 | Pending: 1\nFAILED [T-2]: nope",
        )


if __name__ == "__main__":
    unittest.main()
