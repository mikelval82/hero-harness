import sys
import io
import json
import subprocess
from pathlib import Path
from contextlib import redirect_stdout

from src.harness import harness_utils
from src.harness import registry as _registry

import pytest


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
    out = _capture(harness_utils.cmd_render_prompt, [str(template), "NAME=World", "PLACE=Earth"])
    assert "Hello World, welcome to Earth." in out


def test_render_prompt_with_agent(tmp_path):
    agent = tmp_path / "agent.md"
    agent.write_text("---\nname: tester\n---\nAgent instructions here.")
    template = tmp_path / "template.md"
    template.write_text("Template body with $CLAUDE_HARNESS path.")
    out = _capture(harness_utils.cmd_render_prompt, [
        str(template),
        "--agent", str(agent),
        "--harness-path", "/test/harness",
    ])
    assert "Agent instructions here." in out
    assert "Template body with /test/harness path." in out
    assert "All artifacts live in /test/harness." in out


def test_render_prompt_missing_include(tmp_path):
    template = tmp_path / "template.md"
    template.write_text("Content: {{CONTENT}}")
    out = _capture(harness_utils.cmd_render_prompt, [
        str(template),
        "--include", "CONTENT=/nonexistent/file_that_does_not_exist.md",
    ])
    assert "(not available yet)" in out


def test_cmd_task_info(harness_dir):
    out = _capture(harness_utils.cmd_task_info, ["0"])
    assert 'TASK_ID="1.1"' in out
    assert 'TASK_TITLE="Task one"' in out
    assert 'TASK_STATUS="completed"' in out
    assert 'TASK_COMPLEXITY="M"' in out
    assert 'TASK_COMPLEXITY_REASON="complexity missing; defaulted to M standard route"' in out


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
    md.write_text("# Status\n\n## Files\n- file1.py\n- file2.js\n\n## Other\nstuff")
    out = _capture(harness_utils.cmd_parse_files, [str(md)])
    lines = out.strip().splitlines()
    assert lines == ["file1.py", "file2.js"]


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


from src.integrations import telegram_listener
from src.integrations import telegram_api
from src.integrations import telegram_commands
import urllib.parse
import urllib.request


def test_cmd_read_artifact(tmp_path, monkeypatch):
    (tmp_path / 'spec.md').write_text('# Spec content here')
    sent = []
    monkeypatch.setattr(telegram_api, 'send_message', lambda t, c, msg: sent.append(msg))
    telegram_listener.cmd_read_artifact('fake_token', 'fake_chat', 'spec.md', tmp_path)
    assert len(sent) == 1
    assert '# Spec content here' in sent[0]
    assert '--- spec.md ---' in sent[0]


def test_cmd_read_artifact_not_found(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(telegram_api, 'send_message', lambda t, c, msg: sent.append(msg))
    telegram_listener.cmd_read_artifact('fake_token', 'fake_chat', 'nonexistent.md', tmp_path)
    assert len(sent) == 1
    assert 'not found' in sent[0]



# --- Registry helpers tests (Task 1.1) ---

@pytest.fixture
def registry_file(tmp_path, monkeypatch):
    reg = tmp_path / "_missions.json"
    monkeypatch.setattr(_registry, "REGISTRY_PATH", reg)
    return reg


def test_register_mission_creates_file(registry_file):
    harness_utils.register_mission("myproject:fix-auth", "/home/u/.harness/proj/fix-auth", 1234)
    data = json.loads(registry_file.read_text())
    assert "myproject:fix-auth" in data
    assert data["myproject:fix-auth"]["harness_path"] == "/home/u/.harness/proj/fix-auth"
    assert data["myproject:fix-auth"]["pid"] == 1234
    assert "started" in data["myproject:fix-auth"]


def test_register_mission_overwrites(registry_file):
    harness_utils.register_mission("myproject:fix-auth", "/path/one", 100)
    harness_utils.register_mission("myproject:fix-auth", "/path/two", 200)
    data = json.loads(registry_file.read_text())
    assert data["myproject:fix-auth"]["harness_path"] == "/path/two"
    assert data["myproject:fix-auth"]["pid"] == 200


def test_register_multiple_missions(registry_file):
    harness_utils.register_mission("projA:fix-auth", "/path/a", 100)
    harness_utils.register_mission("projB:add-tests", "/path/b", 200)
    data = json.loads(registry_file.read_text())
    assert "projA:fix-auth" in data
    assert "projB:add-tests" in data
    assert len(data) == 2


def test_unregister_mission_removes(registry_file):
    harness_utils.register_mission("myproject:fix-auth", "/path/a", 100)
    harness_utils.unregister_mission("myproject:fix-auth")
    data = json.loads(registry_file.read_text())
    assert "myproject:fix-auth" not in data


def test_unregister_reduces_remaining_count(registry_file):
    harness_utils.register_mission("projA:branch1", "/path/a", 100)
    harness_utils.register_mission("projB:branch2", "/path/b", 200)
    assert len(harness_utils.list_missions()) == 2
    harness_utils.unregister_mission("projA:branch1")
    remaining = harness_utils.list_missions()
    assert len(remaining) == 1
    assert "projB:branch2" in remaining


def test_unregister_mission_noop(registry_file):
    harness_utils.unregister_mission("nonexistent")


def test_list_missions_no_file(registry_file):
    result = harness_utils.list_missions()
    assert result == {}


def test_list_missions_corrupt_file(registry_file):
    registry_file.write_text("not valid json {{{")
    result = harness_utils.list_missions()
    assert result == {}


def test_register_empty_tag_raises(registry_file):
    with pytest.raises(ValueError):
        harness_utils.register_mission("", "/path/a", 100)


def test_register_empty_path_raises(registry_file):
    with pytest.raises(ValueError):
        harness_utils.register_mission("tag", "", 100)


def test_cli_register_mission(registry_file):
    _capture(harness_utils.cmd_register_mission, ["myproject:my-branch", "/some/path", "9999"])
    data = json.loads(registry_file.read_text())
    assert "myproject:my-branch" in data
    assert data["myproject:my-branch"]["pid"] == 9999


def test_cli_list_missions(registry_file):
    harness_utils.register_mission("proj:branch-a", "/p1", 1)
    harness_utils.register_mission("proj:branch-b", "/p2", 2)
    out = _capture(harness_utils.cmd_list_missions, [])
    parsed = json.loads(out)
    assert "proj:branch-a" in parsed
    assert "proj:branch-b" in parsed


# --- UTF-8 send_message tests ---

def test_send_message_utf8_preserved(monkeypatch):
    captured = []
    def fake_urlopen(url, data=None, timeout=None):
        captured.append(data)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    telegram_api.send_message("tok", "123", "Misión 🚀 completada")
    assert len(captured) == 1
    parsed = urllib.parse.parse_qs(captured[0].decode("utf-8"))
    assert "🚀" in parsed["text"][0]
    assert "Misión" in parsed["text"][0]


def test_send_message_multibyte_chunking(monkeypatch):
    captured = []
    def fake_urlopen(url, data=None, timeout=None):
        captured.append(data)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    text = "a" * (telegram_api.TELEGRAM_MAX_MSG - 1) + "🚀"
    telegram_api.send_message("tok", "123", text)
    assert len(captured) == 1
    parsed = urllib.parse.parse_qs(captured[0].decode("utf-8"))
    assert parsed["text"][0].endswith("🚀")


# --- Emoji boundary chunking + parse_mode tests (Task 1.5) ---


def test_send_message_flag_emoji_boundary(monkeypatch):
    captured = []
    def fake_urlopen(url, data=None, timeout=None):
        captured.append(data)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    text = "a" * 4095 + "🇪🇸"
    telegram_api.send_message("tok", "123", text)
    assert len(captured) == 2
    chunk1 = urllib.parse.parse_qs(captured[0].decode("utf-8"))["text"][0]
    chunk2 = urllib.parse.parse_qs(captured[1].decode("utf-8"))["text"][0]
    assert len(chunk1) == 4095
    assert chunk2 == "🇪🇸"


def test_send_message_skin_tone_boundary(monkeypatch):
    captured = []
    def fake_urlopen(url, data=None, timeout=None):
        captured.append(data)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    text = "a" * 4095 + "👋🏽"
    telegram_api.send_message("tok", "123", text)
    assert len(captured) == 2
    chunk1 = urllib.parse.parse_qs(captured[0].decode("utf-8"))["text"][0]
    chunk2 = urllib.parse.parse_qs(captured[1].decode("utf-8"))["text"][0]
    assert len(chunk1) == 4095
    assert chunk2 == "👋🏽"


def test_send_message_zwj_boundary(monkeypatch):
    captured = []
    def fake_urlopen(url, data=None, timeout=None):
        captured.append(data)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    zwj_seq = "👨‍👩"
    text = "a" * 4094 + zwj_seq
    telegram_api.send_message("tok", "123", text)
    assert len(captured) == 2
    chunk1 = urllib.parse.parse_qs(captured[0].decode("utf-8"))["text"][0]
    chunk2 = urllib.parse.parse_qs(captured[1].decode("utf-8"))["text"][0]
    assert len(chunk1) == 4094
    assert chunk2 == zwj_seq


def test_send_message_parse_mode_included(monkeypatch):
    captured = []
    def fake_urlopen(url, data=None, timeout=None):
        captured.append(data)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    telegram_api.send_message("tok", "123", "hello", parse_mode="HTML")
    assert len(captured) == 1
    parsed = urllib.parse.parse_qs(captured[0].decode("utf-8"))
    assert parsed["parse_mode"][0] == "HTML"


def test_send_message_parse_mode_omitted(monkeypatch):
    captured = []
    def fake_urlopen(url, data=None, timeout=None):
        captured.append(data)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    telegram_api.send_message("tok", "123", "hello")
    assert len(captured) == 1
    parsed = urllib.parse.parse_qs(captured[0].decode("utf-8"))
    assert "parse_mode" not in parsed


# --- resolve_harness tests (Task 1.4) ---

@pytest.fixture
def listener_env(tmp_path, monkeypatch):
    reg = tmp_path / "_missions.json"
    monkeypatch.setattr(_registry, "REGISTRY_PATH", reg)
    default_harness = tmp_path / "default"
    default_harness.mkdir()
    monkeypatch.setattr(telegram_listener, "HARNESS", default_harness)
    return tmp_path, default_harness


def test_resolve_harness_known_tag(listener_env):
    tmp_path, _ = listener_env
    target = tmp_path / "fix-auth"
    target.mkdir()
    harness_utils.register_mission("myproject:fix-auth", str(target), 1234)
    result, resolved_tag = telegram_listener.resolve_harness("myproject:fix-auth")
    assert result == target
    assert resolved_tag == "myproject:fix-auth"


def test_resolve_harness_unknown_tag(listener_env):
    tmp_path, _ = listener_env
    target = tmp_path / "some-mission"
    target.mkdir()
    harness_utils.register_mission("proj:some-branch", str(target), 1)
    result, resolved_tag = telegram_listener.resolve_harness("unknown")
    assert result == target
    assert resolved_tag == "proj:some-branch"


def test_resolve_harness_none_tag(listener_env):
    tmp_path, _ = listener_env
    target = tmp_path / "some-mission"
    target.mkdir()
    harness_utils.register_mission("proj:some-branch", str(target), 1)
    result, resolved_tag = telegram_listener.resolve_harness(None)
    assert result == target
    assert resolved_tag == "proj:some-branch"


def test_resolve_harness_empty_tag(listener_env):
    tmp_path, _ = listener_env
    target = tmp_path / "some-mission"
    target.mkdir()
    harness_utils.register_mission("proj:some-branch", str(target), 1)
    result, resolved_tag = telegram_listener.resolve_harness("")
    assert result == target
    assert resolved_tag == "proj:some-branch"


# --- Dynamic resolution fallback + check_waiting_approval tests (Task 1.3) ---


def test_resolve_harness_empty_registry_fallback(listener_env):
    _, default_harness = listener_env
    result, resolved_tag = telegram_listener.resolve_harness(None)
    assert result == default_harness
    assert resolved_tag is None


def test_check_waiting_approval_iterates_missions(listener_env, monkeypatch):
    tmp_path, _ = listener_env
    m1 = tmp_path / "mission1"
    m1.mkdir()
    m2 = tmp_path / "mission2"
    m2.mkdir()
    harness_utils.register_mission("projA:branch1", str(m1), 1)
    harness_utils.register_mission("projB:branch2", str(m2), 2)
    (m1 / "_waiting_approval").write_text(json.dumps({"verdict": "APPROVED", "task_id": "1.1", "task_title": "A"}))
    (m2 / "_waiting_approval").write_text(json.dumps({"verdict": "APPROVED", "task_id": "2.1", "task_title": "B"}))
    sent = []
    monkeypatch.setattr(telegram_api, "send_message", lambda t, c, msg: sent.append(msg))
    telegram_listener.check_waiting_approval("tok", "123")
    assert len(sent) == 2
    assert (m1 / "_waiting_notified").exists()
    assert (m2 / "_waiting_notified").exists()


def test_check_waiting_approval_empty_registry_fallback(listener_env, monkeypatch):
    _, default_harness = listener_env
    (default_harness / "_waiting_approval").write_text(json.dumps({"verdict": "APPROVED", "task_id": "1.1", "task_title": "T"}))
    sent = []
    monkeypatch.setattr(telegram_api, "send_message", lambda t, c, msg: sent.append(msg))
    telegram_listener.check_waiting_approval("tok", "123")
    assert len(sent) == 1
    assert (default_harness / "_waiting_notified").exists()


# --- Stale registry validation tests (Task 1.4) ---


def test_resolve_harness_stale_known_tag(listener_env):
    tmp_path, _ = listener_env
    stale = tmp_path / "stale-mission"
    valid = tmp_path / "valid-mission"
    valid.mkdir()
    harness_utils.register_mission("proj:stale-branch", str(stale), 1)
    harness_utils.register_mission("proj:valid-branch", str(valid), 2)
    result, resolved_tag = telegram_listener.resolve_harness("proj:stale-branch")
    assert result == valid
    assert resolved_tag == "proj:valid-branch"


def test_resolve_harness_all_stale_fallback(listener_env):
    tmp_path, default_harness = listener_env
    stale = tmp_path / "stale-mission"
    harness_utils.register_mission("proj:stale-branch", str(stale), 1)
    result, resolved_tag = telegram_listener.resolve_harness(None)
    assert result == default_harness
    assert resolved_tag is None


def test_check_waiting_approval_skips_stale(listener_env, monkeypatch):
    tmp_path, _ = listener_env
    stale = tmp_path / "stale-mission"
    valid = tmp_path / "valid-mission"
    valid.mkdir()
    (valid / "_waiting_approval").write_text(json.dumps({"verdict": "APPROVED", "task_id": "1.1", "task_title": "T"}))
    harness_utils.register_mission("proj:stale-branch", str(stale), 1)
    harness_utils.register_mission("proj:valid-branch", str(valid), 2)
    sent = []
    monkeypatch.setattr(telegram_api, "send_message", lambda t, c, msg: sent.append(msg))
    telegram_listener.check_waiting_approval("tok", "123")
    assert len(sent) == 1
    assert (valid / "_waiting_notified").exists()
    assert not (stale / "_waiting_notified").exists()


# --- Directed routing tests (Task 1.5) ---

def test_handle_command_extracts_tag(listener_env, monkeypatch):
    tmp_path, default_harness = listener_env
    target = tmp_path / "fix-auth"
    target.mkdir()
    (target / "_state.json").write_text(json.dumps({
        "phase": "implement", "task_num": 1, "task_count": 3,
        "task_id": "1.1", "task_title": "Test", "completed": "0",
        "mode": "auto", "gate": "auto",
    }))
    harness_utils.register_mission("myproject:fix-auth", str(target), 1234)
    sent = []
    monkeypatch.setattr(telegram_api, "send_message", lambda t, c, msg: sent.append(msg))
    telegram_listener.handle_command("tok", "123", "/status@myproject:fix-auth", default_harness)
    assert len(sent) == 1
    assert "Task 1/3" in sent[0]


def test_handle_command_colon_tag_routing(listener_env, monkeypatch):
    tmp_path, default_harness = listener_env
    target = tmp_path / "proj-branch"
    target.mkdir()
    (target / "_state.json").write_text(json.dumps({
        "phase": "review", "task_num": 3, "task_count": 4,
        "task_id": "2.1", "task_title": "Review", "completed": "1",
        "mode": "auto", "gate": "manual",
    }))
    harness_utils.register_mission("myproject:fix-auth", str(target), 5678)
    sent = []
    monkeypatch.setattr(telegram_api, "send_message", lambda t, c, msg: sent.append(msg))
    telegram_listener.handle_command("tok", "123", "/status@myproject:fix-auth", default_harness)
    assert len(sent) == 1
    assert "Task 3/4" in sent[0]


def test_handle_command_no_tag_uses_default(listener_env, monkeypatch):
    tmp_path, default_harness = listener_env
    (default_harness / "_state.json").write_text(json.dumps({
        "phase": "review", "task_num": 2, "task_count": 5,
        "task_id": "2.1", "task_title": "Default", "completed": "1",
        "mode": "auto", "gate": "manual",
    }))
    sent = []
    monkeypatch.setattr(telegram_api, "send_message", lambda t, c, msg: sent.append(msg))
    telegram_listener.handle_command("tok", "123", "/status", default_harness)
    assert len(sent) == 1
    assert "Task 2/5" in sent[0]


def test_cmd_handlers_accept_harness_param():
    import inspect
    for name, handler in telegram_listener.COMMANDS.items():
        sig = inspect.signature(handler)
        params = list(sig.parameters.keys())
        assert "harness" in params, f"{name} handler missing harness param"


# --- cmd_missions tests (Task 1.6) ---

def test_cmd_missions_empty(listener_env, monkeypatch):
    _, default_harness = listener_env
    sent = []
    monkeypatch.setattr(telegram_api, "send_message", lambda t, c, msg: sent.append(msg))
    telegram_commands.cmd_missions("tok", "123", [], default_harness)
    assert len(sent) == 1
    assert "No active missions" in sent[0]


def test_cmd_missions_with_entries(listener_env, monkeypatch):
    tmp_path, default_harness = listener_env
    mission_dir = tmp_path / "my-mission"
    mission_dir.mkdir()
    (mission_dir / "_state.json").write_text(json.dumps({
        "phase": "implement", "task_num": 2, "task_count": 5,
    }))
    harness_utils.register_mission("myproject:develop", str(mission_dir), 999)
    sent = []
    monkeypatch.setattr(telegram_api, "send_message", lambda t, c, msg: sent.append(msg))
    monkeypatch.setattr(telegram_commands, "_is_pid_alive", lambda pid: True)
    telegram_commands.cmd_missions("tok", "123", [], default_harness)
    assert len(sent) == 1
    assert "@myproject:develop" in sent[0]
    assert "implement" in sent[0]
    assert "2/5" in sent[0]


def test_cmd_missions_missing_state(listener_env, monkeypatch):
    tmp_path, default_harness = listener_env
    mission_dir = tmp_path / "no-state"
    mission_dir.mkdir()
    harness_utils.register_mission("proj:no-state", str(mission_dir), 888)
    sent = []
    monkeypatch.setattr(telegram_api, "send_message", lambda t, c, msg: sent.append(msg))
    monkeypatch.setattr(telegram_commands, "_is_pid_alive", lambda pid: True)
    telegram_commands.cmd_missions("tok", "123", [], default_harness)
    assert len(sent) == 1
    assert "starting..." in sent[0]


# --- _build_ask_prompt tests (Task 2.5) ---


def test_build_ask_prompt_no_artifacts(tmp_path):
    result = telegram_commands._build_ask_prompt("What is this?", tmp_path)
    assert "Answer concisely" in result
    assert "Question: What is this?" in result
    assert "## Mission State" not in result
    assert "## Brainstorm" not in result
    assert "## Spec" not in result


def test_build_ask_prompt_with_state(tmp_path):
    (tmp_path / "_state.json").write_text(json.dumps({
        "phase": "implement",
        "task_id": "1.1",
        "task_title": "Fix bug",
        "task_num": 2,
        "task_count": 5,
    }))
    result = telegram_commands._build_ask_prompt("status?", tmp_path)
    assert "## Mission State" in result
    assert "Phase: implement" in result
    assert "Task 2/5: [1.1] Fix bug" in result


def test_build_ask_prompt_partial_artifacts(tmp_path):
    (tmp_path / "brainstorm.md").write_text("brainstorm ideas")
    (tmp_path / "plan.md").write_text("step 1\nstep 2")
    result = telegram_commands._build_ask_prompt("q?", tmp_path)
    assert "## Brainstorm" in result
    assert "## Plan" in result
    assert "## Spec" not in result
    assert "## Decisions" not in result
    assert "## Tasks" not in result


def test_build_ask_prompt_context_hot(tmp_path):
    (tmp_path / "context-hot.md").write_text("hot content")
    result = telegram_commands._build_ask_prompt("q?", tmp_path)
    assert "## Context" in result
    assert result.count("## Context") == 1
    assert "hot content" in result


def test_build_ask_prompt_corrupt_json(tmp_path):
    (tmp_path / "_state.json").write_text("not json{{")
    result = telegram_commands._build_ask_prompt("q?", tmp_path)
    assert "Question: q?" in result
    assert "Answer concisely" in result
    assert "## Mission State" not in result


# --- _run_claude_ask tests (Task 2.5) ---


def test_run_claude_ask_no_project_dir(tmp_path, monkeypatch):
    captured = {}
    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["input"] = kwargs.get("input")
        return subprocess.CompletedProcess(cmd, 0, stdout="answer", stderr="")
    monkeypatch.setattr(subprocess, "run", fake_run)
    result = telegram_commands._run_claude_ask("test prompt", tmp_path, "/fake/claude")
    assert result == "answer"
    add_dir_indices = [i for i, v in enumerate(captured["cmd"]) if v == "--add-dir"]
    assert len(add_dir_indices) == 1


def test_run_claude_ask_with_project_dir(tmp_path, monkeypatch):
    (tmp_path / "_project_dir").write_text(r"C:\Users\me\project")
    captured = {}
    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")
    monkeypatch.setattr(subprocess, "run", fake_run)
    telegram_commands._run_claude_ask("prompt", tmp_path, "/fake/claude")
    add_dir_indices = [i for i, v in enumerate(captured["cmd"]) if v == "--add-dir"]
    assert len(add_dir_indices) == 2
    assert captured["cmd"][add_dir_indices[1] + 1] == r"C:\Users\me\project"


def test_run_claude_ask_timeout(tmp_path, monkeypatch):
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["/fake/claude"], timeout=120)
    monkeypatch.setattr(subprocess, "run", fake_run)
    result = telegram_commands._run_claude_ask("prompt", tmp_path, "/fake/claude")
    assert result == "Timed out waiting for response."


def test_run_claude_ask_error(tmp_path, monkeypatch):
    def fake_run(cmd, **kwargs):
        raise RuntimeError("connection failed")
    monkeypatch.setattr(subprocess, "run", fake_run)
    result = telegram_commands._run_claude_ask("prompt", tmp_path, "/fake/claude")
    assert result.startswith("Error:")
    assert "connection failed" in result


# --- cmd_ask tests (Task 2.5) ---


def test_cmd_ask_no_args(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(telegram_api, "send_message", lambda t, c, msg: sent.append(msg))
    telegram_listener.cmd_ask("tok", "123", [], tmp_path)
    assert len(sent) == 1
    assert "Usage:" in sent[0]


def test_cmd_ask_no_claude_cmd(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(telegram_api, "send_message", lambda t, c, msg: sent.append(msg))
    telegram_listener.cmd_ask("tok", "123", ["hello"], tmp_path, claude_cmd=None)
    assert len(sent) == 1
    assert "claude CLI not found" in sent[0]


def test_cmd_ask_happy_path(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(telegram_api, "send_message", lambda t, c, msg: sent.append(msg))
    monkeypatch.setattr(telegram_commands, "_build_ask_prompt", lambda q, h: "mock prompt")
    monkeypatch.setattr(telegram_commands, "_run_claude_ask", lambda p, h, c: "mock answer")

    import threading
    captured_target = {}
    class FakeThread:
        def __init__(self, target=None, daemon=None, **kwargs):
            captured_target["fn"] = target
        def start(self):
            pass
    monkeypatch.setattr(threading, "Thread", FakeThread)

    telegram_listener.cmd_ask("tok", "123", ["hello", "world"], tmp_path, claude_cmd="/fake/claude")
    assert sent == ["Thinking..."]

    captured_target["fn"]()
    assert sent == ["Thinking...", "mock answer"]


# --- render_prompt() and load_agent_system() tests (Task 1.3) ---


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
        class_result = harness_utils.PromptRenderer("/h").render(tpl, {"X": "val"}, {})
        func_result = harness_utils.render_prompt(tpl, {"X": "val"}, {}, "/h")
        assert class_result == func_result
