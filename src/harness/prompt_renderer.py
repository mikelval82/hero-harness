"""Prompt template rendering for mission.sh agents."""
from pathlib import Path

_DEFAULT_WORKSPACE_FOOTER = (
    "\n\n## Workspace\n\n"
    "All artifacts live in {path}. "
    "NEVER write artifacts inside the project directory."
)


def strip_frontmatter(text):
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return text
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "".join(lines[i + 1:]).strip()
    return text


class PromptRenderer:

    def __init__(self, harness_path: str):
        self.harness_path = harness_path

    def render(self, template_path, variables: dict, includes: dict) -> str:
        template = Path(template_path).read_text(encoding="utf-8")
        for key, value in variables.items():
            template = template.replace("{{" + key + "}}", value)
        for key, filepath in includes.items():
            p = Path(filepath)
            if p.exists():
                content = p.read_text(encoding="utf-8", errors="replace")
            else:
                content = "(not available yet)"
            template = template.replace("{{" + key + "}}", content)
        template = template.replace("$CLAUDE_HARNESS", self.harness_path)
        return template

    def load_agent_system(self, agent_path) -> str:
        agent_body = strip_frontmatter(Path(agent_path).read_text(encoding="utf-8"))
        agent_body = agent_body.replace("$CLAUDE_HARNESS", self.harness_path)
        return agent_body + _DEFAULT_WORKSPACE_FOOTER.format(path=self.harness_path)


def render_prompt(template_path, variables: dict, includes: dict, harness_path: str) -> str:
    return PromptRenderer(harness_path).render(template_path, variables, includes)


def load_agent_system(agent_path, harness_path: str) -> str:
    return PromptRenderer(harness_path).load_agent_system(agent_path)
