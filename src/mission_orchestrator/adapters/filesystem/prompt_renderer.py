from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path


FRONTMATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)


class FilesystemPromptRenderer:
    def __init__(
        self,
        prompt_dir: Path,
        agent_dir: Path,
        harness_display_path: str,
    ) -> None:
        self.prompt_dir = prompt_dir
        self.agent_dir = agent_dir
        self.harness_display_path = harness_display_path

    def render_user_prompt(
        self,
        template_file: str,
        variables: Mapping[str, str],
        includes: Mapping[str, str],
    ) -> str:
        text = self._read(self.prompt_dir / template_file)
        return self._replace(text, variables | includes)

    def render_system_prompt(self, agent_file: str) -> str:
        text = self._read(self.agent_dir / agent_file)
        text = FRONTMATTER_RE.sub("", text)
        text = self._replace(text, {})
        return (
            text.rstrip()
            + "\n\n## Workspace\n\n"
            + f"All artifacts live in {self.harness_display_path}. "
            + "NEVER write artifacts inside the project directory.\n"
        )

    def _read(self, path: Path) -> str:
        if not path.exists():
            raise FileNotFoundError(path)
        return path.read_text(encoding="utf-8")

    def _replace(self, text: str, values: Mapping[str, str]) -> str:
        rendered = text.replace("$CLAUDE_HARNESS", self.harness_display_path)
        for key, value in values.items():
            rendered = rendered.replace("{{" + key + "}}", value)
        return rendered

