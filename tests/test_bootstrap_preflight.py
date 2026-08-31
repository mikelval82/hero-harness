from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mission_orchestrator.bootstrap import RuntimeConfig, build_runtime
from mission_orchestrator.domain.mission import GateMode, MissionMode


class BootstrapPreflightTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
