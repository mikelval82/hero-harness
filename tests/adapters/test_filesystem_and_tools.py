from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from mission_orchestrator.adapters.filesystem.artifact_store import FilesystemArtifactStore
from mission_orchestrator.adapters.filesystem.task_repository import JsonTaskRepository
from mission_orchestrator.adapters.tools.bash_executor import BashTool
from mission_orchestrator.adapters.tools.bash_policy import BashPolicy
from mission_orchestrator.adapters.tools.file_tools import EditTool, ReadTool, WriteTool
from mission_orchestrator.adapters.tools.path_policy import PathPolicy
from mission_orchestrator.adapters.tools.process_environment import sanitized_child_environment
from mission_orchestrator.adapters.tools.validation_runner import RunValidationTool
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
            self.assertEqual(bash.execute({"command": "echo hello"}, env), "exit=0\nhello")
            self.assertEqual(
                bash.execute({"command": "echo one | cat && echo two"}, env),
                "exit=0\none\ntwo",
            )
            with self.assertRaises(PermissionError):
                bash.execute({"command": "echo $(whoami)"}, env)
            with self.assertRaises(PermissionError):
                bash.execute({"command": "echo no > output.txt"}, env)
            with self.assertRaises(PermissionError):
                bash.execute({"command": "echo no; echo escape"}, env)
            with self.assertRaises(PermissionError):
                ReadTool(policy).execute({"file_path": str(Path(project).parent / "outside.txt")}, env)

    def test_bash_external_process_uses_argv_without_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as harness:
            env = ToolEnvironment(Path(project), Path(harness))
            bash = BashTool(BashPolicy(PathPolicy()))
            completed = SimpleNamespace(stdout="safe\n", stderr="", returncode=0)
            inherited = {
                "PATH": "safe-path",
                "ANTHROPIC_API_KEY": "anthropic-secret",
                "DEEPSEEK_API_KEY": "deepseek-secret",
                "TELEGRAM_TOKEN": "telegram-secret",
                "HARNESS_WORKER_TOKEN": "worker-secret",
                "CLAUDE_HARNESS": "hidden-workspace",
            }
            with patch.dict("os.environ", inherited, clear=True), patch(
                "mission_orchestrator.adapters.tools.bash_executor.subprocess.run",
                return_value=completed,
            ) as run:
                self.assertEqual(bash.execute({"command": "python check.py"}, env), "exit=0\nsafe")

            args, kwargs = run.call_args
            self.assertEqual(args[0], ["python", "check.py"])
            self.assertFalse(kwargs["shell"])
            self.assertEqual(kwargs["env"], {"PATH": "safe-path"})

    def test_policy_rejects_path_and_global_git_escape(self) -> None:
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as harness:
            bash = BashTool(BashPolicy(PathPolicy()))
            env = ToolEnvironment(Path(project), Path(harness))
            with self.assertRaises(PermissionError):
                bash.execute({"command": "cat ../outside.txt"}, env)
            with self.assertRaises(PermissionError):
                bash.execute({"command": "git config --global user.name someone"}, env)
            with self.assertRaises(PermissionError):
                bash.execute({"command": "/bin/sh -c echo"}, env)

    def test_bash_real_child_process_cannot_read_provider_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as harness:
            project_dir = Path(project)
            (project_dir / "env_probe.py").write_text(
                "import os\nprint(os.getenv('DEEPSEEK_API_KEY', 'missing'))\n",
                encoding="utf-8",
            )
            bash = BashTool(BashPolicy(PathPolicy()))
            with patch.dict("os.environ", {"PATH": __import__("os").environ["PATH"], "DEEPSEEK_API_KEY": "secret"}, clear=True):
                result = bash.execute({"command": "python env_probe.py"}, ToolEnvironment(project_dir, Path(harness)))
            self.assertEqual(result, "exit=0\nmissing")

    def test_validation_uses_fixed_runtime_selection_and_sanitized_environment(self) -> None:
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as harness:
            project_dir = Path(project)
            script = project_dir / "mission-validate.cmd"
            script.write_text("@exit /b 0\n", encoding="utf-8")
            tool = RunValidationTool()
            completed = SimpleNamespace(stdout="ok\n", stderr="", returncode=0)
            with patch.dict("os.environ", {"PATH": "safe-path", "DEEPSEEK_API_KEY": "secret"}, clear=True), patch(
                "mission_orchestrator.adapters.tools.validation_runner.subprocess.run",
                return_value=completed,
            ) as run:
                result = tool.execute({"check_id": "target_validation"}, ToolEnvironment(project_dir, Path(harness)))

            self.assertEqual(result, "exit=0\nok")
            args, kwargs = run.call_args
            self.assertEqual(args[0], ["cmd.exe", "/c", str(script)])
            self.assertFalse(kwargs["shell"])
            self.assertEqual(kwargs["env"], {"PATH": "safe-path"})
            with self.assertRaises(ValueError):
                tool.execute({"check_id": "provider_command"}, ToolEnvironment(project_dir, Path(harness)))

    def test_environment_filter_removes_credential_shaped_names(self) -> None:
        filtered = sanitized_child_environment(
            {"PATH": "safe-path", "CUSTOM_SECRET": "no", "GITHUB_TOKEN": "no", "LANG": "en"}
        )
        self.assertEqual(filtered, {"PATH": "safe-path", "LANG": "en"})


if __name__ == "__main__":
    unittest.main()
