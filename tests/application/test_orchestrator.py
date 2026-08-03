from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from mission_orchestrator.adapters.command_bus import QueueCommandBus
from mission_orchestrator.adapters.filesystem.artifact_store import FilesystemArtifactStore
from mission_orchestrator.adapters.filesystem.state_store import FilesystemMissionStateStore
from mission_orchestrator.adapters.filesystem.task_repository import JsonTaskRepository
from mission_orchestrator.application.gate_evaluator import MarkdownGateEvaluator
from mission_orchestrator.application.orchestrator import MissionOrchestrator
from mission_orchestrator.application.services import AppServices
from mission_orchestrator.domain.mission import GateMode, MissionContext, MissionMode
from mission_orchestrator.domain.phase import PhaseResult
from mission_orchestrator.domain.result import MissionOutcome
from mission_orchestrator.domain.task import Task, TaskComplexity
from mission_orchestrator.ports.agent_client import AgentRequest, ConversationRequest
from mission_orchestrator.ports.code_graph import NoopCodeGraphService


class FakeAgent:
    def __init__(self, artifacts: FilesystemArtifactStore, *, fail_first_implement: bool = False) -> None:
        self.artifacts = artifacts
        self.fail_first_implement = fail_first_implement
        self.implement_calls = 0
        self.phases: list[str] = []

    def run_phase(self, request: AgentRequest) -> PhaseResult:
        self.phases.append(request.phase_name)
        phase = request.phase_name
        if phase == "research":
            self.artifacts.write_text("brainstorm.md", "# B\n\nline\nline\n**STATUS: DONE**\n")
        elif phase == "structure":
            if not self.artifacts.exists("tasks.json"):
                self.artifacts.write_text(
                    "tasks.json",
                    json.dumps(
                        [
                            {
                                "id": "T-1",
                                "title": "Implement one",
                                "complexity": "S",
                                "status": "pending",
                                "failure_reason": "",
                            }
                        ]
                    ),
                )
        elif phase == "spec":
            self.artifacts.write_text(
                "spec.md",
                "# Spec\n\n## Objective\nA\n\n## Expected Behavior\nB\n\n**STATUS: DONE**\n",
            )
        elif phase == "plan":
            self.artifacts.write_text("plan.md", "# Plan\n\n## Implementation\nDo it\n\n**STATUS: DONE**\n")
            self.artifacts.write_text("decisions.md", "# Decisions\n")
        elif phase == "implement":
            self.implement_calls += 1
            if self.fail_first_implement and self.implement_calls == 1:
                self.artifacts.write_text("status.md", "# Status\n\n## Files\n- nope.py\n\n**STATUS: BLOCKED**\n")
            else:
                self.artifacts.write_text("status.md", "# Status\n\n## Files\n- ok.py\n\n**STATUS: DONE**\n")
        elif phase == "review":
            self.artifacts.write_text("audit.md", "# Audit\n\n## Verdict\nAPPROVED\n\n**STATUS: DONE**\n")
        elif phase in {"report", "report_plan"}:
            self.artifacts.write_text("mission-report.md", "# Report\n\nDone\n")
        elif phase == "compact":
            self.artifacts.write_text("_compact_tmp.md", "# Compact\n\nDetails\n")
        return PhaseResult("", 1, 0.01, 1, 1)

    def run_conversation(self, request: ConversationRequest) -> PhaseResult:
        self.phases.append(request.phase_name)
        self.artifacts.write_text(
            "brief.md",
            "# Brief\n\n## Objective\nA\n\n## Key Decisions\nB\n\n**STATUS: DONE**\n",
        )
        return PhaseResult("", 1, 0.01, 1, 1)


class FakePrompts:
    def render_user_prompt(self, template_file, variables, includes):  # noqa: ANN001
        return template_file + "\n" + "\n".join(f"{k}={v}" for k, v in variables.items())

    def render_system_prompt(self, agent_file):  # noqa: ANN001
        return agent_file


class FakeTools:
    def schemas_for(self, names):  # noqa: ANN001
        return []

    def execute(self, name, input, env):  # noqa: ANN001
        return ""

    def register(self, tool):  # noqa: ANN001
        return None


class FakeGit:
    def __init__(self) -> None:
        self.merged = False
        self.staged: list[Path] = []

    def detect_base_branch(self) -> str:
        return "main"

    def ensure_develop(self) -> str:
        return "develop"

    def setup_branch(self, branch: str) -> str:
        return branch

    def stage_files(self, files: list[Path]) -> None:
        self.staged.extend(files)

    def final_commit(self, task_description: str, summary: str) -> None:
        return None

    def run_target_validation(self, project_dir: Path) -> bool:
        return True

    def merge_to_develop(self, branch: str) -> bool:
        self.merged = True
        return True


class RecordingNotifier:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.results = []

    def notify(self, message: str) -> None:
        self.messages.append(message)

    def notify_result(self, result) -> None:  # noqa: ANN001
        self.results.append(result)


class NoopLogger:
    def log(self, message: str) -> None:
        return None

    def tool_call(self, name: str, input: dict) -> None:
        return None

    def metric(self, record: dict) -> None:
        return None


def make_services(tmp: Path, mode: MissionMode, *, agent: FakeAgent) -> tuple[AppServices, MissionContext, FakeGit]:
    project = tmp / "project"
    harness = tmp / "harness"
    project.mkdir(exist_ok=True)
    harness.mkdir(exist_ok=True)
    (project / "ok.py").write_text("print('ok')\n", encoding="utf-8")
    artifacts = FilesystemArtifactStore(harness)
    git = FakeGit()
    services = AppServices(
        artifacts=artifacts,
        tasks=JsonTaskRepository(artifacts),
        state=FilesystemMissionStateStore(artifacts, GateMode.AUTO),
        commands=QueueCommandBus(),
        agent=agent,
        tools=FakeTools(),
        prompts=FakePrompts(),
        gates=MarkdownGateEvaluator(artifacts),
        notifier=RecordingNotifier(),
        git=git,
        code_graph=NoopCodeGraphService(),
        logger=NoopLogger(),
    )
    context = MissionContext(
        task="Do mission",
        branch="feature/test",
        mode=mode,
        project_dir=project,
        harness_dir=harness,
        harness_display_path=str(harness),
        gate_mode=GateMode.AUTO,
        no_grill=True,
        max_tasks=20,
        resume=False,
        mission_tag="project:feature-test",
        project_name="project",
    )
    return services, context, git


class OrchestratorTest(unittest.TestCase):
    def test_plan_mode_completes_without_merge(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            agent = FakeAgent(FilesystemArtifactStore(tmp / "harness"))
            services, context, git = make_services(tmp, MissionMode.PLAN, agent=agent)
            agent.artifacts = services.artifacts  # align after service creation
            result = MissionOrchestrator(services, context).run()
            self.assertEqual(result.outcome, MissionOutcome.COMPLETE)
            self.assertFalse(git.merged)
            self.assertIn('"status": "completed"', services.artifacts.read_text("tasks.json"))

    def test_task_failure_does_not_abort_next_task(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            agent = FakeAgent(FilesystemArtifactStore(tmp / "harness"), fail_first_implement=True)
            services, context, git = make_services(tmp, MissionMode.HOTFIX, agent=agent)
            agent.artifacts = services.artifacts
            services.tasks.save(
                [
                    Task("T-1", "bad", complexity=TaskComplexity.S),
                    Task("T-2", "good", complexity=TaskComplexity.S),
                ]
            )
            result = MissionOrchestrator(services, context).run()
            self.assertEqual(result.outcome, MissionOutcome.PARTIAL)
            self.assertTrue(git.merged)
            summary = services.tasks.summary()
            self.assertIn("Completed: 1", summary)
            self.assertIn("Failed: 1", summary)

    def test_missing_structure_blocks(self) -> None:
        class BadStructureAgent(FakeAgent):
            def run_phase(self, request: AgentRequest) -> PhaseResult:
                if request.phase_name == "structure":
                    return PhaseResult("", 1, 0.01, 1, 1)
                return super().run_phase(request)

        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            agent = BadStructureAgent(FilesystemArtifactStore(tmp / "harness"))
            services, context, git = make_services(tmp, MissionMode.FOCUSED, agent=agent)
            agent.artifacts = services.artifacts
            result = MissionOrchestrator(services, context).run()
            self.assertEqual(result.outcome, MissionOutcome.BLOCKED)
            self.assertFalse(git.merged)


if __name__ == "__main__":
    unittest.main()
