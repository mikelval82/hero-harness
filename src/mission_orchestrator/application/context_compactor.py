from __future__ import annotations

from mission_orchestrator.application.phase_executor import PhaseExecutor
from mission_orchestrator.domain.block import BlockReason
from mission_orchestrator.domain.phase import PhaseName


class ContextCompactor:
    def __init__(self, phase_executor: PhaseExecutor) -> None:
        self.phase_executor = phase_executor

    def compact(self, task_label: str = "") -> BlockReason | None:
        artifacts = self.phase_executor.services.artifacts
        if not artifacts.exists("context-hot.md"):
            return None
        outcome = self.phase_executor.run(
            PhaseName.COMPACT,
            variables={"TASK_LABEL": task_label},
            evaluate_gate=False,
        )
        if outcome.block:
            return outcome.block
        if not artifacts.exists("_compact_tmp.md"):
            return None
        tmp = artifacts.read_text("_compact_tmp.md", default="")
        if len(tmp.splitlines()) < 3:
            artifacts.delete("_compact_tmp.md")
            return None
        artifacts.append_text("context-cold.md", "\n\n" + tmp.strip() + "\n")
        artifacts.delete("_compact_tmp.md")
        artifacts.delete("context-hot.md")
        return None

