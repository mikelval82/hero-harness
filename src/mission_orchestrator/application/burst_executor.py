from __future__ import annotations

import re

from mission_orchestrator.application.phase_executor import PhaseExecutor
from mission_orchestrator.domain.block import BlockReason
from mission_orchestrator.domain.phase import PhaseName
from mission_orchestrator.domain.task import Task


STEP_RE = re.compile(r"^###\s+\d+[\).]?\s*(.+)$", re.MULTILINE)


class BurstExecutor:
    def __init__(self, phase_executor: PhaseExecutor) -> None:
        self.phase_executor = phase_executor

    def run(self, task: Task) -> BlockReason | None:
        artifacts = self.phase_executor.services.artifacts
        plan = artifacts.read_text("plan.md", default="")
        steps = [match.group(0).strip() for match in STEP_RE.finditer(plan)]
        if not steps:
            return self.phase_executor.run(
                PhaseName.IMPLEMENT,
                variables={"TASK_ID": task.id, "TASK_TITLE": task.title},
            ).block
        for index, step in enumerate(steps, start=1):
            progress = artifacts.read_text("_burst_progress.md", default="(not available yet)")
            final = index == len(steps)
            variables = {
                "TASK_ID": task.id,
                "TASK_TITLE": task.title,
                "PLAN_STEP": step,
                "PROGRESS": progress,
                "BURST_FINAL_INSTRUCTIONS": self._final_instructions() if final else "",
            }
            outcome = self.phase_executor.run(
                PhaseName.IMPLEMENT_BURSTS,
                variables=variables,
                evaluate_gate=final,
            )
            if outcome.block:
                return outcome.block
            new_progress = artifacts.read_text("_burst_progress.md", default="")
            if len(new_progress) <= len(progress) and f"Step {index}:" not in new_progress:
                artifacts.append_text("_burst_progress.md", f"\nStep {index}: done\n")
        return None

    @staticmethod
    def _final_instructions() -> str:
        return (
            "This is the last burst. Create status.md from scratch, run mission-validate.* "
            "when present, and list modified files under ## Files."
        )

