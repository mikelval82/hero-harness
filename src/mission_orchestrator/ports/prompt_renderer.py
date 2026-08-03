from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol


class PromptRenderer(Protocol):
    def render_user_prompt(
        self,
        template_file: str,
        variables: Mapping[str, str],
        includes: Mapping[str, str],
    ) -> str: ...

    def render_system_prompt(self, agent_file: str) -> str: ...

