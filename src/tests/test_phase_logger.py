import sys
from pathlib import Path

from src.harness import phase_logger
from src.harness.phase_logger import describe_tool, make_tool_callback, _write_metric, TOOL_LABELS, PhaseLogger, _get_logger, _INSTANCES


class TestDescribeTool:
    def test_read(self):
        assert describe_tool("Read", {"file_path": "/a/b/foo.py"}) == "Reading foo.py"

    def test_read_windows(self):
        assert describe_tool("Read", {"file_path": "C:\\a\\b\\foo.py"}) == "Reading foo.py"

    def test_edit(self):
        assert describe_tool("Edit", {"file_path": "/x/bar.ts"}) == "Editing bar.ts"

    def test_write(self):
        assert describe_tool("Write", {"file_path": "/x/out.md"}) == "Writing out.md"

    def test_bash(self):
        assert describe_tool("Bash", {"command": "echo hello"}) == "Running: echo hello"

    def test_bash_truncation(self):
        long_cmd = "a" * 80
        result = describe_tool("Bash", {"command": long_cmd})
        assert result.endswith("...")
        assert len(result) == len("Running: ") + 60 + 3

    def test_grep(self):
        assert describe_tool("Grep", {"pattern": "TODO"}) == "Searching 'TODO'"

    def test_glob(self):
        assert describe_tool("Glob", {"pattern": "*.py"}) == "Finding files *.py"

    def test_unknown(self):
        assert describe_tool("CustomTool", {}) == "CustomTool"


class TestMakeToolCallback:
    def test_callback_writes_log_and_progress(self, tmp_path):
        cb = make_tool_callback(tmp_path)
        cb("Read", {"file_path": "/a/b/foo.py"})

        log_content = (tmp_path / "mission.log").read_text(encoding="utf-8")
        assert "  > " in log_content
        assert "Reading foo.py" in log_content

        progress_content = (tmp_path / "_progress.txt").read_text(encoding="utf-8")
        assert "Reading foo.py" in progress_content
        assert "  > " not in progress_content

    def test_log_appends(self, tmp_path):
        cb = make_tool_callback(tmp_path)
        cb("Read", {"file_path": "/a/foo.py"})
        cb("Edit", {"file_path": "/a/bar.py"})

        lines = (tmp_path / "mission.log").read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2

    def test_progress_overwrites(self, tmp_path):
        cb = make_tool_callback(tmp_path)
        cb("Read", {"file_path": "/a/first.py"})
        cb("Edit", {"file_path": "/a/second.py"})

        progress = (tmp_path / "_progress.txt").read_text(encoding="utf-8")
        assert "second.py" in progress
        assert "first.py" not in progress

    def test_custom_log_file(self, tmp_path):
        custom_log = tmp_path / "custom.log"
        cb = make_tool_callback(tmp_path, log_file=custom_log)
        cb("Bash", {"command": "ls"})

        assert custom_log.exists()
        assert "Running: ls" in custom_log.read_text(encoding="utf-8")
        assert not (tmp_path / "mission.log").exists()

    def test_missing_harness_dir_no_crash(self, tmp_path):
        nonexistent = tmp_path / "does" / "not" / "exist"
        cb = make_tool_callback(nonexistent)
        cb("Read", {"file_path": "/a/foo.py"})

    def test_log_line_format(self, tmp_path, monkeypatch):
        monkeypatch.setattr(phase_logger, "timestamp", lambda: "12:34:56")
        cb = make_tool_callback(tmp_path)
        cb("Read", {"file_path": "/a/b/foo.py"})

        content = (tmp_path / "mission.log").read_text(encoding="utf-8")
        assert content == "[12:34:56]   > Reading foo.py\n"

    def test_progress_line_format(self, tmp_path, monkeypatch):
        monkeypatch.setattr(phase_logger, "timestamp", lambda: "12:34:56")
        cb = make_tool_callback(tmp_path)
        cb("Read", {"file_path": "/a/b/foo.py"})

        content = (tmp_path / "_progress.txt").read_text(encoding="utf-8")
        assert content == "[12:34:56] Reading foo.py"


class TestWriteMetric:
    def test_creates_jsonl(self, tmp_path):
        import json
        _write_metric(tmp_path, "implement[1.3]", turns=10, elapsed=45.67,
                      input_tokens=5000, output_tokens=1200, result="success")
        lines = (tmp_path / "_metrics.jsonl").read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["phase"] == "implement[1.3]"
        assert record["turns"] == 10
        assert record["elapsed_s"] == 45.7
        assert record["input_tokens"] == 5000
        assert record["output_tokens"] == 1200
        assert record["result"] == "success"
        assert "timestamp" in record

        telemetry = json.loads((tmp_path / "_telemetry.jsonl").read_text(encoding="utf-8").strip())
        assert telemetry["event_type"] == "phase_result"
        assert telemetry["cost"]["total_tokens"] == 6200
        assert telemetry["cost"]["missing_component"] == "model_pricing"

    def test_appends(self, tmp_path):
        _write_metric(tmp_path, "spec[1]", turns=1, elapsed=1.0,
                      input_tokens=100, output_tokens=50, result="success")
        _write_metric(tmp_path, "plan[1]", turns=2, elapsed=2.0,
                      input_tokens=200, output_tokens=100, result="timeout")
        lines = (tmp_path / "_metrics.jsonl").read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2

    def test_defaults_when_no_kwargs(self, tmp_path):
        import json
        _write_metric(tmp_path, "test", result="gate_fail")
        record = json.loads((tmp_path / "_metrics.jsonl").read_text(encoding="utf-8").strip())
        assert record["turns"] == 0
        assert record["elapsed_s"] == 0
        assert record["input_tokens"] == 0
        assert record["output_tokens"] == 0

    def test_swallows_errors(self, tmp_path):
        nonexistent = tmp_path / "does" / "not" / "exist"
        _write_metric(nonexistent, "test", result="success")


class TestPhaseLogger:
    def test_log_writes_to_file(self, tmp_path):
        logger = PhaseLogger(tmp_path)
        logger.log("hello world")
        content = (tmp_path / "mission.log").read_text(encoding="utf-8")
        assert "hello world" in content

    def test_log_custom_file(self, tmp_path):
        custom = tmp_path / "custom.log"
        logger = PhaseLogger(tmp_path, log_file=custom)
        logger.log("custom msg")
        assert custom.exists()
        assert "custom msg" in custom.read_text(encoding="utf-8")
        assert not (tmp_path / "mission.log").exists()

    def test_on_tool_call_writes_log_and_progress(self, tmp_path):
        logger = PhaseLogger(tmp_path)
        logger.on_tool_call("Read", {"file_path": "/a/b/foo.py"})
        log_content = (tmp_path / "mission.log").read_text(encoding="utf-8")
        assert "Reading foo.py" in log_content
        progress = (tmp_path / "_progress.txt").read_text(encoding="utf-8")
        assert "Reading foo.py" in progress

    def test_write_metric_creates_jsonl(self, tmp_path):
        import json
        logger = PhaseLogger(tmp_path)
        logger.write_metric("spec[1]", turns=3, elapsed=12.5,
                            input_tokens=1000, output_tokens=500, result="success")
        record = json.loads((tmp_path / "_metrics.jsonl").read_text(encoding="utf-8").strip())
        assert record["phase"] == "spec[1]"
        assert record["turns"] == 3
        assert record["result"] == "success"

    def test_shared_instance_log_and_callback(self, tmp_path):
        logger = PhaseLogger(tmp_path)
        logger.log("phase start")
        logger.on_tool_call("Bash", {"command": "echo hi"})
        logger.log("phase end")
        lines = (tmp_path / "mission.log").read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 3

    def test_factory_functions_return_bound_methods(self, tmp_path):
        log_fn = make_tool_callback(tmp_path)
        log_fn("Grep", {"pattern": "test"})
        assert (tmp_path / "mission.log").exists()


class TestGetLogger:
    def test_caches_instance(self, tmp_path):
        _INSTANCES.clear()
        a = _get_logger(tmp_path)
        b = _get_logger(tmp_path)
        assert a is b
        _INSTANCES.clear()

    def test_different_harness_different_instance(self, tmp_path):
        _INSTANCES.clear()
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        a = _get_logger(dir_a)
        b = _get_logger(dir_b)
        assert a is not b
        _INSTANCES.clear()

    def test_factories_share_instance(self, tmp_path):
        _INSTANCES.clear()
        log_fn = make_tool_callback(tmp_path)
        log_fn2 = make_tool_callback(tmp_path)
        assert log_fn.__self__ is log_fn2.__self__
        _INSTANCES.clear()
