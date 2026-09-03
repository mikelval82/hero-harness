from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mission_orchestrator.bootstrap import RuntimeConfig, build_runtime, model_capabilities
from mission_orchestrator.cli import _telegram_config
from mission_orchestrator.domain.mission import GateMode, MissionMode


class BootstrapPreflightTest(unittest.TestCase):
    def test_deepseek_uses_flash_for_routine_work_and_pro_for_deep_work(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(
                model_capabilities("deepseek"),
                {
                    "cheap": "deepseek-v4-flash",
                    "default": "deepseek-v4-flash",
                    "deep": "deepseek-v4-pro",
                },
            )

    def test_model_tiers_are_configurable_and_global_model_remains_forced(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "HARNESS_MODEL_CHEAP": "fast",
                "HARNESS_MODEL_DEFAULT": "daily",
                "HARNESS_MODEL_DEEP": "planner",
            },
            clear=True,
        ):
            self.assertEqual(
                model_capabilities("deepseek"),
                {"cheap": "fast", "default": "daily", "deep": "planner"},
            )
            self.assertEqual(
                model_capabilities("deepseek", "forced"),
                {"cheap": "forced", "default": "forced", "deep": "forced"},
            )

    def test_mutating_preflight_runs_before_workspace_setup(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            config = RuntimeConfig(
                task="task",
                branch="feature/safe",
                mode=MissionMode.FULL,
                project_dir=Path(raw),
                gate_mode=GateMode.AUTO,
            )
            with patch(
                "mission_orchestrator.bootstrap.SubprocessGitService.preflight",
                side_effect=RuntimeError("dirty worktree"),
            ), patch("mission_orchestrator.bootstrap.WorkspaceManager.setup") as setup:
                with self.assertRaisesRegex(RuntimeError, "dirty worktree"):
                    build_runtime(config)
            setup.assert_not_called()

    def test_partial_telegram_configuration_is_rejected(self) -> None:
        with patch.dict("os.environ", {"TELEGRAM_TOKEN": "token"}, clear=True):
            with self.assertRaisesRegex(ValueError, "configured together"):
                _telegram_config()


if __name__ == "__main__":
    unittest.main()
