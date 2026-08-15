from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from mission_orchestrator.adapters.command_bus import QueueCommandBus
from mission_orchestrator.adapters.design.store import DesignStore
from mission_orchestrator.adapters.filesystem.artifact_store import FilesystemArtifactStore
from mission_orchestrator.adapters.filesystem.state_store import FilesystemMissionStateStore
from mission_orchestrator.adapters.filesystem.task_repository import JsonTaskRepository
from mission_orchestrator.application.gate_evaluator import MarkdownGateEvaluator
from mission_orchestrator.application.orchestrator import MissionOrchestrator
from mission_orchestrator.application.plan_compiler import PlanCompiler
from mission_orchestrator.application.services import AppServices
from mission_orchestrator.domain.command import Command, CommandKind
from mission_orchestrator.domain.mission import GateMode, MissionContext, MissionMode
from mission_orchestrator.domain.phase import PhaseResult
from mission_orchestrator.domain.result import MissionOutcome
from mission_orchestrator.domain.task import Task
from mission_orchestrator.domain.workplan import validate_plan
from mission_orchestrator.ports.agent_client import AgentRequest, ConversationRequest
from mission_orchestrator.ports.code_graph import NoopCodeGraphService


def _task(task_id: str, covers: list[str], dependencies: list[str] | None = None) -> Task:
    return Task(task_id, f"Task {task_id}", covers=covers, dependencies=dependencies or [])


class ValidatePlanTest(unittest.TestCase):
    def test_d1_exact_coverage_and_valid_deps(self) -> None:
        tasks = [_task("T-1", ["create:a"]), _task("T-2", ["change:b"], dependencies=["T-1"])]
        self.assertEqual(validate_plan(["create:a", "change:b"], tasks), [])

    def test_d2_coverage_errors(self) -> None:
        uncovered = validate_plan(["create:a", "change:b"], [_task("T-1", ["create:a"])])
        self.assertTrue(any("change:b" in error for error in uncovered))
        duplicated = validate_plan(
            ["create:a"], [_task("T-1", ["create:a"]), _task("T-2", ["create:a"])]
        )
        self.assertTrue(any("create:a" in error for error in duplicated))
        unknown = validate_plan(["create:a"], [_task("T-1", ["create:a", "create:ghost"])])
        self.assertTrue(any("create:ghost" in error for error in unknown))

    def test_d3_dependency_errors(self) -> None:
        missing = validate_plan(["create:a"], [_task("T-1", ["create:a"], dependencies=["T-9"])])
        self.assertTrue(any("T-9" in error for error in missing))
        selfdep = validate_plan(["create:a"], [_task("T-1", ["create:a"], dependencies=["T-1"])])
        self.assertTrue(any("itself" in error for error in selfdep))
        cyclic = validate_plan(
            ["create:a", "create:b"],
            [
                _task("T-1", ["create:a"], dependencies=["T-2"]),
                _task("T-2", ["create:b"], dependencies=["T-1"]),
            ],
        )
        self.assertTrue(any("cycle" in error.lower() for error in cyclic))


class TaskRoundtripTest(unittest.TestCase):
    def test_d4_new_fields_roundtrip_and_legacy_load(self) -> None:
        task = Task(
            "T-1",
            "Title",
            covers=["create:a"],
            dependencies=["T-0"],
            target_nodes=["cache"],
        )
        loaded = Task.from_json(task.to_json())
        self.assertEqual(loaded.covers, ["create:a"])
        self.assertEqual(loaded.dependencies, ["T-0"])
        self.assertEqual(loaded.target_nodes, ["cache"])
        legacy = Task.from_json({"id": "T-2", "title": "Old", "complexity": "S", "status": "pending"})
        self.assertEqual(legacy.covers, [])
        self.assertEqual(legacy.dependencies, [])
        self.assertEqual(legacy.target_nodes, [])


class PlanCompilerTest(unittest.TestCase):
    def test_d5_compiles_changeset_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            harness = Path(raw)
            artifacts = FilesystemArtifactStore(harness)
            compiler = PlanCompiler(harness, artifacts)
            self.assertFalse(compiler.compile())
            snapshot = {
                "snapshot_id": "snap-x",
                "design_revision": 1,
                "observed_revision": 0,
                "nodes": [
                    {
                        "id": "cache",
                        "label": "Cache",
                        "level": "CODE",
                        "provenance": "AGENT",
                        "location": "IN_REPOSITORY",
                        "intent": "CREATE",
                        "parent_id": None,
                        "locator": "src/cache.py:Cache",
                        "description": "",
                    }
                ],
                "edges": [],
            }
            artifacts.write_text("approved_snapshot.json", json.dumps(snapshot))
            self.assertTrue(compiler.compile())
            changeset = json.loads(artifacts.read_text("changeset.json"))
            self.assertEqual(changeset["snapshot_id"], "snap-x")
            self.assertEqual([op["id"] for op in changeset["operations"]], ["create:cache"])


class MappedFakeAgent:
    def __init__(self, artifacts: FilesystemArtifactStore, *, cover_everything: bool = True) -> None:
        self.artifacts = artifacts
        self.cover_everything = cover_everything

    def run_phase(self, request: AgentRequest) -> PhaseResult:
        phase = request.phase_name
        if phase == "research":
            self.artifacts.write_text("brainstorm.md", "# B\n\nline\nline\n**STATUS: DONE**\n")
        elif phase == "structure":
            covers = ["create:cache"] if self.cover_everything else []
            self.artifacts.write_text(
                "tasks.json",
                json.dumps(
                    [
                        {
                            "id": "T-1",
                            "title": "Create cache",
                            "complexity": "S",
                            "status": "pending",
                            "failure_reason": "",
                            "covers": covers,
                            "dependencies": [],
                            "target_nodes": ["cache"],
                        }
                    ]
                ),
            )
        elif phase == "spec":
            self.artifacts.write_text(
                "spec.md",
                "# Spec\n\n## Objective\nCreate cache\n\n## Expected Behavior\nCache exists\n\n**STATUS: DONE**\n",
            )
        elif phase == "plan":
            self.artifacts.write_text(
                "plan.md",
                "# Plan\n\n## Implementation\nCreate cache\n\n**STATUS: DONE**\n",
            )
            self.artifacts.write_text("decisions.md", "# Decisions\n")
        elif phase == "implement":
            self.artifacts.write_text("status.md", "# Status\n\n## Files\n- ok.py\n\n**STATUS: DONE**\n")
        elif phase in {"report", "report_plan"}:
            self.artifacts.write_text("mission-report.md", "# Report\n\nDone\n")
        return PhaseResult("", 1, 0.01, 1, 1)

    def run_conversation(self, request: ConversationRequest) -> PhaseResult:
        return PhaseResult("", 1, 0.01, 1, 1)


class _Notifier:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def notify(self, message: str) -> None:
        self.messages.append(message)

    def notify_result(self, result) -> None:  # noqa: ANN001
        pass


class _Prompts:
    def render_user_prompt(self, template_file, variables, includes):  # noqa: ANN001
        return template_file

    def render_system_prompt(self, agent_file):  # noqa: ANN001
        return agent_file


class _Tools:
    def schemas_for(self, names):  # noqa: ANN001
        return []

    def execute(self, name, input, env):  # noqa: ANN001
        return ""

    def register(self, tool):  # noqa: ANN001
        return None


class _Git:
    def ensure_develop(self) -> str:
        return "develop"

    def setup_branch(self, branch: str) -> str:
        return branch

    def current_commit(self) -> str:
        return "test-head"

    def stage_files(self, files) -> None:  # noqa: ANN001
        pass

    def final_commit(self, task_description: str, summary: str) -> None:
        pass

    def merge_to_develop(self, branch: str) -> bool:
        return True


class _Logger:
    def log(self, message: str) -> None:
        pass

    def tool_call(self, name: str, input: dict) -> None:
        pass

    def metric(self, record: dict) -> None:
        pass


def _mapped_mission(tmp: Path, *, cover_everything: bool = True):
    project = tmp / "project"
    harness = tmp / "harness"
    scope = tmp / "scope"
    for path in (project, harness, scope):
        path.mkdir(exist_ok=True)
    (project / "ok.py").write_text("print('ok')\n", encoding="utf-8")
    artifacts = FilesystemArtifactStore(harness)
    agent = MappedFakeAgent(artifacts, cover_everything=cover_everything)
    commands = QueueCommandBus()
    services = AppServices(
        artifacts=artifacts,
        tasks=JsonTaskRepository(artifacts),
        state=FilesystemMissionStateStore(artifacts, GateMode.AUTO),
        commands=commands,
        agent=agent,
        tools=_Tools(),
        prompts=_Prompts(),
        gates=MarkdownGateEvaluator(artifacts),
        notifier=_Notifier(),
        git=_Git(),
        code_graph=NoopCodeGraphService(),
        logger=_Logger(),
    )
    context = MissionContext(
        task="Do mission",
        branch="feature/test",
        mode=MissionMode.FOCUSED,
        project_dir=project,
        harness_dir=harness,
        harness_display_path=str(harness),
        gate_mode=GateMode.AUTO,
        no_grill=True,
        max_tasks=20,
        resume=False,
        mission_tag="project:feature-test",
        project_name="project",
        project_scope_dir=scope,
    )
    DesignStore(harness / "design.db").apply(
        operation_id="seed",
        author="AGENT",
        base_revision=0,
        operations=[
            {
                "op": "add_node",
                "id": "cache",
                "label": "Cache",
                "level": "CODE",
                "provenance": "AGENT",
                "location": "IN_REPOSITORY",
                "intent": "CREATE",
                "locator": "src/cache.py:Cache",
            }
        ],
    )
    return services, context, commands


class MappedPipelineTest(unittest.TestCase):
    def test_d6_approved_map_compiles_and_completes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            services, context, commands = _mapped_mission(tmp)
            commands.publish(Command(CommandKind.APPROVE))
            result = MissionOrchestrator(services, context).run()
            self.assertEqual(result.outcome, MissionOutcome.COMPLETE)
            self.assertTrue(services.artifacts.exists("approved_snapshot.json"))
            self.assertTrue(services.artifacts.exists("changeset.json"))

    def test_d7_uncovered_operations_block_structure(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            services, context, commands = _mapped_mission(tmp, cover_everything=False)
            commands.publish(Command(CommandKind.APPROVE))
            result = MissionOrchestrator(services, context).run()
            self.assertEqual(result.outcome, MissionOutcome.BLOCKED)
            self.assertIn("create:cache", str(result.block))

    def test_d8_rejected_map_blocks_without_changeset(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            services, context, commands = _mapped_mission(tmp)
            commands.publish(Command(CommandKind.REJECT, reason="wrong shape"))
            result = MissionOrchestrator(services, context).run()
            self.assertEqual(result.outcome, MissionOutcome.BLOCKED)
            self.assertFalse(services.artifacts.exists("changeset.json"))


if __name__ == "__main__":
    unittest.main()
