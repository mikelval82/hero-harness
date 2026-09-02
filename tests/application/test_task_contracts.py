from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from mission_orchestrator.adapters.filesystem.artifact_store import FilesystemArtifactStore
from mission_orchestrator.application.phase_registry import PHASES
from mission_orchestrator.application.task_contracts import TaskContractCompiler
from mission_orchestrator.domain.phase import PhaseName
from mission_orchestrator.domain.task import Task


class TaskContractCompilerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.artifacts = FilesystemArtifactStore(Path(self.temporary.name))
        self.snapshot = {
            "snapshot_id": "snap-7",
            "design_revision": 12,
            "observed_revision": 3,
            "brief": {"logical_id": "mission/brief", "revision": 4},
            "project": {"name": "sample", "path": "C:/sample"},
            "base_commit": "abc123",
            "nodes": [
                {
                    "id": "telegram-module",
                    "label": "Telegram module",
                    "level": "PACKAGE",
                    "provenance": "AGENT",
                    "location": "IN_REPOSITORY",
                    "intent": "CREATE",
                    "parent_id": None,
                    "locator": "src/telegram/notifier.py",
                    "description": "Telegram integration",
                    "kind": "module",
                    "target_path": "src/telegram/notifier.py",
                    "qualified_name": "",
                    "signature": "",
                    "docstring": "Telegram integration module.",
                    "satisfies": ["REQ-2"],
                    "acceptance": ["Module can be imported"],
                },
                {
                    "id": "telegram-notifier",
                    "label": "TelegramNotifier",
                    "level": "CODE",
                    "provenance": "AGENT",
                    "location": "IN_REPOSITORY",
                    "intent": "CREATE",
                    "parent_id": "telegram-module",
                    "locator": "src/telegram/notifier.py:TelegramNotifier",
                    "description": "Sends notifications",
                    "kind": "class",
                    "target_path": "src/telegram/notifier.py",
                    "qualified_name": "TelegramNotifier",
                    "signature": "",
                    "docstring": "Send Telegram notifications.",
                    "satisfies": ["REQ-7"],
                    "acceptance": ["Message delivery is reported"],
                },
            ],
            "edges": [
                {
                    "source": "telegram-module",
                    "target": "telegram-notifier",
                    "relation": "contains",
                    "provenance": "AGENT",
                    "intent": "CREATE",
                }
            ],
        }
        self.changeset = {
            "snapshot_id": "snap-7",
            "operations": [
                {
                    "id": "create:telegram-notifier",
                    "kind": "CREATE_NODE",
                    "target_node": "telegram-notifier",
                    "locator": "src/telegram/notifier.py:TelegramNotifier",
                    "node_kind": "class",
                    "target_path": "src/telegram/notifier.py",
                    "qualified_name": "TelegramNotifier",
                    "signature": "",
                    "docstring": "Send Telegram notifications.",
                    "satisfies": ["REQ-7"],
                    "acceptance": ["Message delivery is reported"],
                    "level": "CODE",
                    "location": "IN_REPOSITORY",
                    "depends_on": [],
                    "description": "Sends notifications",
                    "source": None,
                    "target": None,
                    "relation": None,
                    "verification_level": "hard",
                }
            ],
            "skipped": [],
            "issues": [],
        }
        self.artifacts.write_text(
            "approved_snapshot.json",
            json.dumps(self.snapshot),
        )
        self.artifacts.write_text("changeset.json", json.dumps(self.changeset))

    def test_cde_a06_generates_byte_stable_complete_slice(self) -> None:
        task = Task.from_json(
            {
                "id": "T-1",
                "title": "Implement notifier",
                "covers": ["create:telegram-notifier"],
                "dependencies": [],
                "target_nodes": ["telegram-notifier"],
            }
        )
        compiler = TaskContractCompiler(self.artifacts)

        paths = compiler.compile([task])
        first = self.artifacts.read_text(paths["T-1"])
        second_paths = compiler.compile([task])
        second = self.artifacts.read_text(second_paths["T-1"])

        self.assertEqual(first, second)
        payload = json.loads(first)
        self.assertEqual(payload["snapshot_id"], "snap-7")
        self.assertEqual(payload["design_revision"], 12)
        self.assertEqual(payload["brief"]["revision"], 4)
        self.assertEqual(payload["base_commit"], "abc123")
        self.assertEqual(payload["requirements"], ["REQ-2", "REQ-7"])
        self.assertEqual(
            payload["validation_obligations"],
            [
                {
                    "check_id": "target_validation",
                    "expected": "Message delivery is reported",
                    "id": "VO:telegram-notifier:1",
                    "kind": "trusted_command",
                    "provenance": "task_contract",
                    "requirement_ids": ["ACC:telegram-notifier:1", "REQ-7"],
                    "target": "src/telegram/notifier.py",
                },
            ],
        )
        self.assertNotIn(
            "VO:telegram-module:1",
            {item["id"] for item in payload["validation_obligations"]},
        )
        self.assertEqual(
            [operation["id"] for operation in payload["operations"]],
            ["create:telegram-notifier"],
        )
        self.assertEqual(
            [node["id"] for node in payload["nodes"]],
            ["telegram-module", "telegram-notifier"],
        )
        self.assertEqual(payload["relationships"][0]["verification_level"], "hard")

    def test_generation_rejects_unknown_operation_or_node(self) -> None:
        compiler = TaskContractCompiler(self.artifacts)
        with self.assertRaisesRegex(ValueError, "unknown operation"):
            compiler.compile([Task(id="T-1", title="Bad", covers=["missing"])])
        with self.assertRaisesRegex(ValueError, "unknown target node"):
            compiler.compile(
                [
                    Task(
                        id="T-2",
                        title="Bad node",
                        covers=["create:telegram-notifier"],
                        target_nodes=["missing"],
                    )
                ]
            )

    def test_materialize_exposes_the_exact_immutable_slice(self) -> None:
        task = Task(
            id="T-1",
            title="Implement notifier",
            covers=["create:telegram-notifier"],
            target_nodes=["telegram-notifier"],
        )
        compiler = TaskContractCompiler(self.artifacts)
        path = compiler.compile([task])[task.id]

        compiler.materialize(task.id)

        self.assertEqual(
            self.artifacts.read_text("task-contract.json"),
            self.artifacts.read_text(path),
        )

    def test_cde_a07_all_contractual_phases_share_task_contract_include(self) -> None:
        for phase in (
            PhaseName.SPEC,
            PhaseName.PLAN,
            PhaseName.IMPLEMENT,
            PhaseName.IMPLEMENT_BURSTS,
            PhaseName.REVIEW,
            PhaseName.REIMPLEMENT,
        ):
            with self.subTest(phase=phase.value):
                self.assertEqual(PHASES[phase].includes["TASK_CONTRACT"], "task-contract.json")


if __name__ == "__main__":
    unittest.main()
