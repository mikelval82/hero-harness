from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from mission_orchestrator.adapters.filesystem.artifact_store import FilesystemArtifactStore
from mission_orchestrator.application.context_compactor import ContextCompactor
from mission_orchestrator.application.contract_verifier import (
    ContractCheckState,
    PythonContractVerifier,
)
from mission_orchestrator.application.phase_executor import PhaseExecutor
from mission_orchestrator.application.review_coordinator import ReviewCoordinator
from mission_orchestrator.domain.mission import MissionMode
from mission_orchestrator.domain.task import Task, TaskStatus

from tests.application.test_orchestrator import FakeAgent, make_services


def _node(node_id: str, kind: str, qualified_name: str, **overrides) -> dict:
    node = {
        "id": node_id,
        "kind": kind,
        "target_path": "src/telegram/notifier.py",
        "qualified_name": qualified_name,
        "signature": "",
        "docstring": "Required documentation.",
        "satisfies": [],
        "acceptance": [],
        "location": "IN_REPOSITORY",
        "intent": "CREATE",
    }
    node.update(overrides)
    return node


def _contract(nodes: list[dict], relationships: list[dict] | None = None) -> dict:
    return {
        "schema_version": 1,
        "snapshot_id": "snap-1",
        "design_revision": 1,
        "brief": {"logical_id": "mission/brief", "revision": 1},
        "project": {"name": "sample", "path": "C:/sample"},
        "base_commit": "abc",
        "task": {"id": "T-1", "title": "Telegram", "covers": [], "dependencies": [], "target_nodes": []},
        "requirements": [],
        "operations": [],
        "nodes": nodes,
        "relationships": relationships or [],
    }


class PythonContractVerifierTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)
        source = self.project / "src" / "telegram" / "notifier.py"
        source.parent.mkdir(parents=True)
        source.write_text(
            '''"""Telegram integration."""

class BaseNotifier:
    """Base notifier."""

class TelegramNotifier(BaseNotifier):
    """Send Telegram notifications."""

    def send(self, chat_id: str, text: str = "hello") -> bool:
        """Send one message."""
        return True
''',
            encoding="utf-8",
        )

    def test_cde_a08_correct_declarations_and_hard_relations_pass(self) -> None:
        contract = _contract(
            [
                _node("module", "module", "", docstring="Telegram module."),
                _node("base", "class", "BaseNotifier"),
                _node("notifier", "class", "TelegramNotifier"),
                _node(
                    "send",
                    "method",
                    "TelegramNotifier.send",
                    signature='(self, chat_id: str, text: str = "hello") -> bool',
                ),
            ],
            [
                {"source": "module", "target": "notifier", "relation": "contains", "verification_level": "hard"},
                {"source": "notifier", "target": "send", "relation": "contains", "verification_level": "hard"},
                {"source": "notifier", "target": "base", "relation": "inherits", "verification_level": "hard"},
                {"source": "send", "target": "base", "relation": "uses", "verification_level": "advisory"},
            ],
        )

        result = PythonContractVerifier(self.project).verify(contract)

        self.assertTrue(result.passed)
        self.assertFalse(
            [check for check in result.checks if check.state is ContractCheckState.FAILED]
        )
        self.assertTrue(
            any(check.field == "relationship.inherits" for check in result.checks)
        )

    def test_cde_a09_wrong_signature_and_missing_docstring_are_field_level_failures(self) -> None:
        source = self.project / "src" / "telegram" / "notifier.py"
        source.write_text(
            "class TelegramNotifier:\n"
            "    def send(self, chat_id: int, text: str):\n"
            "        return None\n",
            encoding="utf-8",
        )
        contract = _contract(
            [
                _node(
                    "send",
                    "method",
                    "TelegramNotifier.send",
                    signature='(self, chat_id: str, text: str = "hello") -> bool',
                )
            ]
        )

        result = PythonContractVerifier(self.project).verify(contract)

        self.assertFalse(result.passed)
        fields = {check.field for check in result.checks if check.state is ContractCheckState.FAILED}
        self.assertIn("signature.chat_id.annotation", fields)
        self.assertIn("signature.text.default", fields)
        self.assertIn("signature.return", fields)
        self.assertIn("docstring", fields)

    def test_missing_path_and_wrong_kind_are_blocking(self) -> None:
        result = PythonContractVerifier(self.project).verify(
            _contract(
                [
                    _node("missing", "class", "Missing", target_path="src/missing.py"),
                    _node("wrong", "function", "TelegramNotifier"),
                ]
            )
        )

        self.assertFalse(result.passed)
        failed = {(check.node_id, check.field) for check in result.checks if check.state is ContractCheckState.FAILED}
        self.assertIn(("missing", "target_path"), failed)
        self.assertIn(("wrong", "kind"), failed)


class MissionContractEnforcementTest(unittest.TestCase):
    def test_cde_a09_task_is_not_completed_when_contract_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            agent = FakeAgent(FilesystemArtifactStore(tmp / "harness"))
            services, context, _ = make_services(tmp, MissionMode.HOTFIX, agent=agent)
            agent.artifacts = services.artifacts
            task = Task("T-1", "Implement Telegram")
            services.tasks.save([task])
            services.artifacts.write_text(
                "task-contract.json",
                json.dumps(
                    _contract(
                        [
                            _node(
                                "missing",
                                "class",
                                "Missing",
                                target_path="src/missing.py",
                            )
                        ]
                    )
                ),
            )
            phase_executor = PhaseExecutor(services, context)
            review = ReviewCoordinator(
                services,
                context,
                phase_executor,
                ContextCompactor(phase_executor),
            )

            block = review.approve_without_review(0, task)

            self.assertIsNotNone(block)
            self.assertIn("target_path", str(block))
            self.assertIs(services.tasks.load()[0].status, TaskStatus.PENDING)
            report = json.loads(services.artifacts.read_text("contract-verification.json"))
            self.assertFalse(report["passed"])


if __name__ == "__main__":
    unittest.main()
