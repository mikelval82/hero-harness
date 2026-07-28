import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from src.harness import harness_utils


def _capture(fn, *args):
    """Call fn(*args) and return captured stdout as string."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        fn(*args)
    return buf.getvalue()


@pytest.fixture
def harness_dir(tmp_path, monkeypatch):
    tasks = [
        {"id": "1.1", "title": "Task one", "status": "completed"},
        {"id": "1.2", "title": "Task two"},
        {"id": "1.3", "title": "Task three", "status": "failed"},
    ]
    (tmp_path / "tasks.json").write_text(json.dumps(tasks, indent=2))
    monkeypatch.setattr(harness_utils, "HARNESS", tmp_path)
    return tmp_path


def test_strip_frontmatter_normal():
    text = "---\nkey: val\n---\nbody content"
    assert harness_utils.strip_frontmatter(text) == "body content"


def test_strip_frontmatter_no_frontmatter():
    text = "just plain text\nno frontmatter here"
    assert harness_utils.strip_frontmatter(text) == text


def test_strip_frontmatter_unclosed():
    text = "---\nkey: val\nno closing delimiter"
    assert harness_utils.strip_frontmatter(text) == text


def test_shell_escape_special_chars():
    assert harness_utils._shell_escape("\\") == "\\\\"
    assert harness_utils._shell_escape("$") == "\\$"
    assert harness_utils._shell_escape("`") == "\\`"
    assert harness_utils._shell_escape('"') == '\\"'
    assert harness_utils._shell_escape("\n") == " "
    assert harness_utils._shell_escape("\r") == ""


def test_shell_escape_empty():
    assert harness_utils._shell_escape("") == ""


def test_shell_escape_all_at_once():
    raw = 'a\\b$c`d"e\nf\rg'
    escaped = harness_utils._shell_escape(raw)
    assert escaped == 'a\\\\b\\$c\\`d\\"e fg'


def test_render_prompt_basic(tmp_path):
    template = tmp_path / "template.md"
    template.write_text("Hello {{NAME}}, welcome to {{PLACE}}.")
    out = _capture(
        harness_utils.cmd_render_prompt,
        [str(template), "NAME=World", "PLACE=Earth"],
    )
    assert "Hello World, welcome to Earth." in out


def test_render_prompt_with_agent(tmp_path):
    agent = tmp_path / "agent.md"
    agent.write_text("---\nname: tester\n---\nAgent instructions here.")
    template = tmp_path / "template.md"
    template.write_text("Template body with $CLAUDE_HARNESS path.")
    out = _capture(
        harness_utils.cmd_render_prompt,
        [
            str(template),
            "--agent",
            str(agent),
            "--harness-path",
            "/test/harness",
        ],
    )
    assert "Agent instructions here." in out
    assert "Template body with /test/harness path." in out
    assert "All artifacts live in /test/harness." in out


def test_render_prompt_missing_include(tmp_path):
    template = tmp_path / "template.md"
    template.write_text("Content: {{CONTENT}}")
    out = _capture(
        harness_utils.cmd_render_prompt,
        [
            str(template),
            "--include",
            "CONTENT=/nonexistent/file_that_does_not_exist.md",
        ],
    )
    assert "(not available yet)" in out


def test_cmd_task_info(harness_dir):
    out = _capture(harness_utils.cmd_task_info, ["0"])
    assert 'TASK_ID="1.1"' in out
    assert 'TASK_TITLE="Task one"' in out
    assert 'TASK_STATUS="completed"' in out
    assert 'TASK_COMPLEXITY="M"' in out
    assert (
        'TASK_COMPLEXITY_REASON="complexity missing; defaulted to M standard route"'
        in out
    )


def test_cmd_task_info_default_status(harness_dir):
    out = _capture(harness_utils.cmd_task_info, ["1"])
    assert 'TASK_STATUS="pending"' in out


def test_cmd_task_count(harness_dir):
    out = _capture(harness_utils.cmd_task_count, [])
    assert out.strip() == "3"


def test_cmd_update_task(harness_dir):
    harness_utils.cmd_update_task(["1", "completed"])
    tasks = json.loads((harness_dir / "tasks.json").read_text())
    assert tasks[1]["status"] == "completed"


def test_cmd_task_summary(harness_dir):
    out = _capture(harness_utils.cmd_task_summary, [])
    assert "Total: 3" in out
    assert "Completed: 1" in out
    assert "Failed: 1" in out
    assert "Pending: 1" in out
    assert "[COMPLETED] 1.1: Task one" in out
    assert "[PENDING] 1.2: Task two" in out
    assert "[FAILED] 1.3: Task three" in out


def test_parse_files_normal(tmp_path):
    md = tmp_path / "status.md"
    md.write_text(
        "# Status\n\n## Files\n- file1.py\n- file2.js\n\n## Other\nstuff"
    )
    out = _capture(harness_utils.cmd_parse_files, [str(md)])
    assert out.strip().splitlines() == ["file1.py", "file2.js"]


def test_parse_files_no_section(tmp_path):
    md = tmp_path / "status.md"
    md.write_text("# Status\n\nNo files section here.")
    out = _capture(harness_utils.cmd_parse_files, [str(md)])
    assert out.strip() == ""


def test_parse_files_empty_section(tmp_path):
    md = tmp_path / "status.md"
    md.write_text("## Files\n## Next Section\nstuff")
    out = _capture(harness_utils.cmd_parse_files, [str(md)])
    assert out.strip() == ""


def test_setup_harness_has_no_multimission_identity(tmp_path, monkeypatch):
    project = tmp_path / "my project"
    project.mkdir()
    harness_root = tmp_path / "home"
    harness_root.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: harness_root))
    monkeypatch.setattr(
        harness_utils,
        "stage_project_memory",
        lambda *args, **kwargs: {"persistent": "memory", "staged": "staged-memory"},
    )
    monkeypatch.setattr(
        harness_utils,
        "stage_retrieved_cases",
        lambda *args, **kwargs: {"persistent": "cases", "staged": "staged-cases"},
    )
    monkeypatch.setattr(
        harness_utils,
        "stage_retrieved_skills",
        lambda *args, **kwargs: {
            "persistent": "skills",
            "staged": "staged-skills",
            "generated": "generated-skills",
        },
    )

    result = harness_utils.setup_harness("feature/single", True, cwd=project)

    assert "mission_tag" not in result
    assert result["project_name"] == "myproject"
    assert result["branch_safe"] == "feature-single"
    assert result["harness"] == (
        harness_root / ".harness" / "myproject" / "feature-single"
    )
    assert (result["harness"] / "_project_dir").read_text(encoding="utf-8") == str(
        project.resolve()
    )
    assert (result["harness"] / "_gate_mode").read_text(encoding="utf-8") == "manual"


def test_render_prompt_returns_string(tmp_path):
    template = tmp_path / "template.md"
    template.write_text("Hello {{NAME}}, welcome to {{PLACE}}.")
    result = harness_utils.render_prompt(
        template, {"NAME": "World", "PLACE": "Earth"}, {}, "/test/harness"
    )
    assert result == "Hello World, welcome to Earth."


def test_render_prompt_includes_from_file(tmp_path):
    template = tmp_path / "template.md"
    template.write_text("Content: {{SPEC}}")
    include_file = tmp_path / "spec.md"
    include_file.write_text("Specification body here")
    result = harness_utils.render_prompt(
        template, {}, {"SPEC": str(include_file)}, "/h"
    )
    assert "Specification body here" in result


def test_render_prompt_includes_missing_file(tmp_path):
    template = tmp_path / "template.md"
    template.write_text("Content: {{SPEC}}")
    result = harness_utils.render_prompt(
        template, {}, {"SPEC": "/nonexistent/file.md"}, "/h"
    )
    assert "(not available yet)" in result


def test_render_prompt_harness_replacement(tmp_path):
    template = tmp_path / "template.md"
    template.write_text("Path is $CLAUDE_HARNESS here.")
    result = harness_utils.render_prompt(template, {}, {}, "/my/harness")
    assert result == "Path is /my/harness here."


def test_render_prompt_does_not_print(tmp_path, capsys):
    template = tmp_path / "template.md"
    template.write_text("Hello {{NAME}}")
    harness_utils.render_prompt(template, {"NAME": "X"}, {}, "/h")
    captured = capsys.readouterr()
    assert captured.out == ""


def test_load_agent_system_returns_string(tmp_path):
    agent = tmp_path / "agent.md"
    agent.write_text("---\nname: tester\n---\nAgent body with $CLAUDE_HARNESS path.")
    result = harness_utils.load_agent_system(agent, "/test/harness")
    assert "Agent body with /test/harness path." in result
    assert "---" not in result
    assert "name: tester" not in result
    assert "All artifacts live in /test/harness." in result


def test_load_agent_system_no_frontmatter(tmp_path):
    agent = tmp_path / "agent.md"
    agent.write_text("Plain agent body.")
    result = harness_utils.load_agent_system(agent, "/h")
    assert result.startswith("Plain agent body.")
    assert "All artifacts live in /h." in result


def test_burst_prompt_contains_spec_regrounding_contract():
    text = Path("prompts/implement-burst-prompt.md").read_text(encoding="utf-8")
    assert "## Spec re-grounding" in text
    assert "Objective" in text
    assert "Acceptance criteria" in text
    assert "Constraints" in text
    assert "Non-goals" in text
    assert "Current failed checks or risks" in text
    assert "Progress from prior bursts" in text


def test_reimplement_prompt_contains_spec_regrounding_contract():
    text = Path("prompts/reimplement-prompt.md").read_text(encoding="utf-8")
    assert "## Spec re-grounding" in text
    assert "Objective" in text
    assert "Acceptance criteria" in text
    assert "Constraints" in text
    assert "Non-goals" in text
    assert "Current failed checks" in text
    assert "reviewer audit" in text
    assert "## Diagnosis" in text


def test_implementer_prompts_contain_self_verification_contract():
    implement_text = Path("prompts/implement-prompt.md").read_text(encoding="utf-8")
    reimplement_text = Path("prompts/reimplement-prompt.md").read_text(encoding="utf-8")
    agent_text = Path("agents/implementer.md").read_text(encoding="utf-8")
    for text in (implement_text, reimplement_text, agent_text):
        assert "## Self-Verification" in text
        assert "tests_run" in text
        assert "acceptance_criteria_checked" in text
        assert "edge_cases_considered" in text
        assert "files_touched_reviewed" in text
        assert "harness_artifacts_not_written_to_target" in text
        assert "known_risks" in text


class TestPromptRenderer:
    def test_render_variables(self, tmp_path):
        tpl = tmp_path / "tpl.md"
        tpl.write_text("Hello {{NAME}}, task {{TASK}}")
        renderer = harness_utils.PromptRenderer("/harness")
        result = renderer.render(tpl, {"NAME": "world", "TASK": "test"}, {})
        assert result == "Hello world, task test"

    def test_render_includes(self, tmp_path):
        tpl = tmp_path / "tpl.md"
        tpl.write_text("Data: {{SPEC}}")
        spec = tmp_path / "spec.md"
        spec.write_text("spec content here")
        renderer = harness_utils.PromptRenderer("/h")
        result = renderer.render(tpl, {}, {"SPEC": str(spec)})
        assert "spec content here" in result

    def test_render_missing_include(self, tmp_path):
        tpl = tmp_path / "tpl.md"
        tpl.write_text("Data: {{SPEC}}")
        renderer = harness_utils.PromptRenderer("/h")
        result = renderer.render(tpl, {}, {"SPEC": "/nonexistent/spec.md"})
        assert "(not available yet)" in result

    def test_render_harness_replacement(self, tmp_path):
        tpl = tmp_path / "tpl.md"
        tpl.write_text("Path is $CLAUDE_HARNESS")
        renderer = harness_utils.PromptRenderer("/my/harness")
        result = renderer.render(tpl, {}, {})
        assert "/my/harness" in result

    def test_load_agent_system(self, tmp_path):
        agent = tmp_path / "agent.md"
        agent.write_text("---\nname: test\n---\nAgent body $CLAUDE_HARNESS")
        renderer = harness_utils.PromptRenderer("/h")
        result = renderer.load_agent_system(agent)
        assert "Agent body /h" in result
        assert "All artifacts live in /h" in result
        assert "---" not in result

    def test_factory_functions_match_class(self, tmp_path):
        tpl = tmp_path / "tpl.md"
        tpl.write_text("{{X}}")
        class_result = harness_utils.PromptRenderer("/h").render(
            tpl, {"X": "val"}, {}
        )
        func_result = harness_utils.render_prompt(tpl, {"X": "val"}, {}, "/h")
        assert class_result == func_result
