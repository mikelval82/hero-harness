from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from mission_orchestrator.adapters.filesystem.artifact_store import FilesystemArtifactStore
from mission_orchestrator.adapters.filesystem.task_repository import JsonTaskRepository
from mission_orchestrator.adapters.tools.bash_executor import BashTool
from mission_orchestrator.adapters.tools.bash_policy import BashPolicy
from mission_orchestrator.adapters.tools.file_tools import EditTool, ReadTool, WriteTool
from mission_orchestrator.adapters.tools.path_policy import PathPolicy
from mission_orchestrator.domain.task import TaskStatus
from mission_orchestrator.ports.tool_registry import ToolEnvironment


class FilesystemAndToolsTest(unittest.TestCase):
    def test_artifact_store_retries_transient_windows_replace_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = FilesystemArtifactStore(Path(tmp))
            real_replace = __import__("os").replace
            attempts = 0

            def transient_replace(source, target):  # noqa: ANN001
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    raise PermissionError(5, "Access denied")
                return real_replace(source, target)

            with patch(
                "mission_orchestrator.adapters.filesystem.artifact_store.os.replace",
                side_effect=transient_replace,
            ):
                store.write_text("tasks.json", "[]")

            self.assertEqual(store.read_text("tasks.json"), "[]")
            self.assertEqual(attempts, 2)

    def test_artifact_store_blocks_escape_and_task_repo_roundtrips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = FilesystemArtifactStore(Path(tmp))
            with self.assertRaises(ValueError):
                store.write_text("../escape.txt", "bad")
            store.write_text(
                "tasks.json",
                '[{"id":"T-1","title":"Do it","complexity":"S","status":"pending","failure_reason":""}]',
            )
            repo = JsonTaskRepository(store)
            tasks = repo.load()
            self.assertEqual(tasks[0].id, "T-1")
            repo.update(0, TaskStatus.COMPLETED)
            self.assertIn('"status": "completed"', store.read_text("tasks.json"))

    def test_file_tools_and_bash_policy(self) -> None:
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as harness:
            env = ToolEnvironment(Path(project), Path(harness))
            policy = PathPolicy()
            WriteTool(policy).execute({"file_path": "hello.txt", "content": "one\ntwo\n"}, env)
            self.assertIn("1: one", ReadTool(policy).execute({"file_path": "hello.txt"}, env))
            EditTool(policy).execute(
                {"file_path": "hello.txt", "old_string": "two", "new_string": "three"},
                env,
            )
            self.assertIn("three", (Path(project) / "hello.txt").read_text(encoding="utf-8"))
            bash = BashTool(BashPolicy(policy))
            self.assertEqual(bash.execute({"command": "echo hello"}, env), "hello")
            with self.assertRaises(PermissionError):
                bash.execute({"command": "echo $(whoami)"}, env)
            with self.assertRaises(PermissionError):
                ReadTool(policy).execute({"file_path": str(Path(project).parent / "outside.txt")}, env)


if __name__ == "__main__":
    unittest.main()

