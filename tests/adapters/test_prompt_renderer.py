from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from mission_orchestrator.adapters.filesystem.prompt_renderer import FilesystemPromptRenderer


class PromptRendererTest(unittest.TestCase):
    def test_implement_prompt_names_the_authorized_project_root(self) -> None:
        repository = Path(__file__).resolve().parents[2]
        renderer = FilesystemPromptRenderer(
            repository / "prompts",
            repository / "agents",
            "/safe/harness",
        )

        rendered = renderer.render_user_prompt(
            "implement-prompt.md",
            {
                "TASK_ID": "task-1",
                "TASK_TITLE": "Implement adapter",
                "PROJECT_DIR": "/safe/project-worktree",
            },
            {
                "SPEC": "spec",
                "PLAN": "plan",
                "DECISIONS": "decisions",
                "CONTEXT_COLD": "cold",
                "CONTEXT_HOT": "hot",
                "TASK_CONTRACT": "contract",
                "GRAPH_INSTRUCTIONS": "graph",
            },
        )

        self.assertIn("Authorized project root: `/safe/project-worktree`", rendered)
        self.assertIn("repository-relative paths", rendered)
        self.assertIn("Do not use the original checkout", rendered)


if __name__ == "__main__":
    unittest.main()
