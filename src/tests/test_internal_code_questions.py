from __future__ import annotations

import json
import copy
import sqlite3
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.agent.code_graph_tool import MAX_CODE_GRAPH_ROWS, _tool_code_graph
from src.agent.loop import PhaseResult, PhaseTimeout, run_conversation, run_phase
from src.integrations.code_questions import (
    ANSWER_MAX_CHARS,
    ASK_MAX_TOOL_RESULT,
    ASK_MAX_TOKENS,
    ASK_MAX_TURNS,
    ASK_TIMEOUT_SECONDS,
    ASK_TOOL_NAMES,
    CodeQuestionService,
    QUESTION_MAX_CHARS,
)


def _text_block(text: str):
    return SimpleNamespace(type="text", text=text)


def _tool_block(name: str, inp: dict, tool_id: str = "tool-1"):
    return SimpleNamespace(type="tool_use", name=name, input=inp, id=tool_id)


def _response(stop_reason: str, blocks: list, *, input_tokens: int = 10, output_tokens: int = 5):
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=blocks,
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


class _FakeMessages:
    def __init__(self, responses: list):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        return self.responses.pop(0)


class _FakeClient:
    def __init__(self, responses: list):
        self.messages = _FakeMessages(responses)


def _make_graph_db(harness: Path, *, bulk_nodes: int = 0) -> Path:
    db_path = harness / "code_graph.db"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        "CREATE TABLE nodes (id TEXT PRIMARY KEY, type TEXT NOT NULL, file TEXT NOT NULL);"
        "CREATE TABLE edges (source TEXT NOT NULL, target TEXT NOT NULL, relation TEXT NOT NULL);"
    )
    connection.executemany(
        "INSERT INTO nodes(id, type, file) VALUES (?, ?, ?)",
        [
            ("a.py", "module", "a.py"),
            ("a.py:caller", "function", "a.py"),
            ("b.py:target", "function", "b.py"),
            ("c.py:unused", "function", "c.py"),
        ],
    )
    connection.executemany(
        "INSERT INTO edges(source, target, relation) VALUES (?, ?, ?)",
        [
            ("a.py", "a.py:caller", "defines"),
            ("a.py:caller", "b.py:target", "calls"),
        ],
    )
    if bulk_nodes:
        connection.executemany(
            "INSERT INTO nodes(id, type, file) VALUES (?, 'function', 'bulk.py')",
            [(f"bulk.py:f{i:03}",) for i in range(bulk_nodes)],
        )
    connection.commit()
    connection.close()
    return db_path


def _query_graph(harness: Path, inp: dict) -> dict:
    raw = _tool_code_graph(inp, harness / "project", harness)
    assert not raw.startswith("Error:"), raw
    return json.loads(raw)


def test_code_graph_native_tool_supports_all_read_only_actions(tmp_path):
    harness = tmp_path / "harness"
    harness.mkdir()
    db_path = _make_graph_db(harness)
    before = db_path.read_bytes()

    found = _query_graph(harness, {"action": "find_nodes", "pattern": "TARGET"})
    assert found["rows"] == [["function", "b.py:target", "b.py"]]

    dependencies = _query_graph(
        harness, {"action": "dependencies", "node": "a.py:caller"}
    )
    assert dependencies["rows"] == [["calls", "function", "b.py:target", "b.py"]]

    dependents = _query_graph(
        harness, {"action": "dependents", "node": "b.py:target"}
    )
    assert dependents["rows"] == [["calls", "function", "a.py:caller", "a.py"]]

    impact = _query_graph(
        harness, {"action": "impact_analysis", "node": "b.py:target"}
    )
    assert [row[1] for row in impact["rows"]] == ["a.py", "a.py:caller"]

    dead = _query_graph(harness, {"action": "dead_code"})
    assert {row[1] for row in dead["rows"]} == {"a.py:caller", "c.py:unused"}
    assert db_path.read_bytes() == before


def test_code_graph_queries_are_parameterized_bounded_and_recoverable(tmp_path):
    harness = tmp_path / "harness"
    harness.mkdir()
    _make_graph_db(harness, bulk_nodes=MAX_CODE_GRAPH_ROWS + 5)

    injection = _query_graph(
        harness, {"action": "find_nodes", "pattern": "%' OR 1=1 --"}
    )
    assert injection["count"] == 0

    bounded = _query_graph(harness, {"action": "find_nodes", "pattern": "bulk.py:f"})
    assert bounded["count"] == MAX_CODE_GRAPH_ROWS

    unsupported = _tool_code_graph({"action": "build"}, tmp_path, harness)
    assert unsupported.startswith("Error: code graph unavailable:")
    assert "unsupported action" in unsupported

    invalid_limit = _tool_code_graph(
        {"action": "dead_code", "limit": MAX_CODE_GRAPH_ROWS + 1}, tmp_path, harness
    )
    assert "limit must be between" in invalid_limit

    missing = _tool_code_graph({"action": "dead_code"}, tmp_path, tmp_path / "missing")
    assert "code_graph.db is not available" in missing

    for forbidden in ("sql", "db_path", "command", "interpreter"):
        denied = _tool_code_graph(
            {"action": "dead_code", forbidden: "not allowed"}, tmp_path, harness,
        )
        assert "unexpected field" in denied

    wrong_action_field = _tool_code_graph(
        {"action": "dead_code", "node": "a.py:caller"}, tmp_path, harness,
    )
    assert "unexpected field" in wrong_action_field

    (harness / "code_graph.invalid").write_text("failed rebuild\n", encoding="utf-8")
    stale = _tool_code_graph({"action": "dead_code"}, tmp_path, harness)
    assert "failed rebuild" in stale


def test_agent_runner_blocks_unannounced_tool_and_honors_custom_limits(tmp_path):
    client = _FakeClient(
        [
            _response("tool_use", [_tool_block("Write", {"file_path": "x", "content": "bad"})]),
            _response("end_turn", [_text_block("safe")]),
        ]
    )
    with patch("src.agent.loop.execute_tool") as execute:
        result = run_phase(
            client,
            system_prompt="system",
            user_prompt="question",
            tools=[{"name": "Read"}],
            phase_name="guard",
            project_dir=tmp_path,
            harness_dir=tmp_path,
            max_tokens=42,
            max_tool_result=20,
        )

    assert result.text == "safe"
    execute.assert_not_called()
    assert client.messages.calls[0]["max_tokens"] == 42
    denied = client.messages.calls[1]["messages"][-1]["content"][0]
    assert denied["is_error"] is True
    assert denied["content"].startswith("Error: tool 'Write'")
    assert denied["content"].endswith("... [truncated]")


def test_blocked_tool_cannot_trigger_a_tool_completion_condition(tmp_path):
    client = _FakeClient(
        [
            _response("tool_use", [_tool_block("Write", {"file_path": "x", "content": "bad"})]),
            _response("end_turn", []),
        ]
    )
    result = run_conversation(
        client,
        system_prompt="system",
        user_prompt="question",
        tools=[{"name": "Read"}],
        phase_name="guard",
        project_dir=tmp_path,
        harness_dir=tmp_path,
        get_human_input=lambda _text: "continue",
        should_stop_after_tools=lambda _blocks: True,
    )
    assert result.turns == 2


def test_code_question_service_uses_read_only_tools_brief_context_and_safe_telemetry(tmp_path):
    project = tmp_path / "project"
    harness = tmp_path / "harness"
    project.mkdir()
    harness.mkdir()
    (harness / "_state.json").write_text(
        json.dumps(
            {
                "phase": "implement",
                "task_id": "T1",
                "task_title": "Harden Telegram",
                "task_num": 1,
                "task_count": 2,
            }
        ),
        encoding="utf-8",
    )
    (harness / "plan.md").write_text("ARTIFACT_SECRET_MUST_NOT_BE_PROMPTED", encoding="utf-8")
    answer_secret = "ANSWER_SECRET_" + "x" * ANSWER_MAX_CHARS
    client = _FakeClient([_response("end_turn", [_text_block(answer_secret)], input_tokens=31, output_tokens=17)])
    service = CodeQuestionService(client, project_dir=project, harness_dir=harness)
    delivered: list[str] = []
    done = threading.Event()

    question = "QUESTION_SECRET: where is the router?"
    assert service.ask(question, lambda text: (delivered.append(text), done.set())) is True
    assert done.wait(2)
    assert len(delivered[0]) == ANSWER_MAX_CHARS
    assert delivered[0].endswith("…")

    request = client.messages.calls[0]
    assert request["max_tokens"] == ASK_MAX_TOKENS
    assert tuple(tool["name"] for tool in request["tools"]) == ASK_TOOL_NAMES
    prompt = request["messages"][0]["content"]
    assert question in prompt
    assert "phase=implement" in prompt
    assert "ARTIFACT_SECRET_MUST_NOT_BE_PROMPTED" not in prompt

    telemetry = (harness / "_telemetry.jsonl").read_text(encoding="utf-8")
    event = json.loads(telemetry)
    assert event["event_type"] == "phase_result"
    assert event["phase"] == "telegram_ask"
    assert event["result"] == "success"
    assert event["turns"] == 1
    assert event["cost"]["input_tokens"] == 31
    assert "QUESTION_SECRET" not in telemetry
    assert "ANSWER_SECRET" not in telemetry


def test_code_question_service_configures_bounded_agent_run(tmp_path):
    project = tmp_path / "project"
    harness = tmp_path / "harness"
    project.mkdir()
    harness.mkdir()
    service = CodeQuestionService(_FakeClient([]), project_dir=project, harness_dir=harness)
    captured: dict = {}
    done = threading.Event()

    def fake_run(**kwargs):
        captured.update(kwargs)
        return PhaseResult("answer", 1, 0.1, 2, 1, service.model)

    with patch.object(service.runner, "run_phase", side_effect=fake_run):
        assert service.ask("Where?", lambda _text: done.set())
        assert done.wait(2)

    assert captured["timeout"] == ASK_TIMEOUT_SECONDS
    assert captured["max_turns"] == ASK_MAX_TURNS
    assert captured["max_tokens"] == ASK_MAX_TOKENS
    assert captured["max_tool_result"] == ASK_MAX_TOOL_RESULT
    assert tuple(tool["name"] for tool in captured["tools"]) == ASK_TOOL_NAMES


def test_code_question_service_disables_sdk_retries_for_shared_deadline(tmp_path):
    project = tmp_path / "project"
    harness = tmp_path / "harness"
    project.mkdir()
    harness.mkdir()
    options = {}

    class Client(_FakeClient):
        def with_options(self, **kwargs):
            options.update(kwargs)
            return self

    CodeQuestionService(Client([]), project_dir=project, harness_dir=harness)

    assert options == {"timeout": ASK_TIMEOUT_SECONDS, "max_retries": 0}


def test_code_question_service_executes_code_graph_then_read(tmp_path):
    project = tmp_path / "project"
    harness = tmp_path / "harness"
    project.mkdir()
    harness.mkdir()
    source = project / "a.py"
    source.write_text("def caller():\n    return 1\n", encoding="utf-8")
    worktree_before = {
        path.relative_to(project): path.read_bytes()
        for path in project.rglob("*")
        if path.is_file()
    }
    _make_graph_db(harness)
    client = _FakeClient(
        [
            _response(
                "tool_use",
                [_tool_block("CodeGraph", {"action": "find_nodes", "pattern": "caller"}, "cg")],
            ),
            _response(
                "tool_use",
                [_tool_block("Read", {"file_path": str(source)}, "read")],
            ),
            _response("end_turn", [_text_block("Verified in a.py.")]),
        ]
    )
    service = CodeQuestionService(client, project_dir=project, harness_dir=harness)
    delivered: list[str] = []
    done = threading.Event()

    assert service.ask("Where is caller?", lambda text: (delivered.append(text), done.set()))
    assert done.wait(2)
    assert delivered == ["Verified in a.py."]
    graph_result = client.messages.calls[1]["messages"][-1]["content"][0]["content"]
    read_result = client.messages.calls[2]["messages"][-1]["content"][0]["content"]
    assert "a.py:caller" in graph_result
    assert "def caller" in read_result
    worktree_after = {
        path.relative_to(project): path.read_bytes()
        for path in project.rglob("*")
        if path.is_file()
    }
    assert worktree_after == worktree_before


def test_code_question_service_rejects_long_and_concurrent_questions(tmp_path):
    project = tmp_path / "project"
    harness = tmp_path / "harness"
    project.mkdir()
    harness.mkdir()
    entered = threading.Event()
    release = threading.Event()

    class BlockingMessages:
        def create(self, **_kwargs):
            entered.set()
            assert release.wait(2)
            return _response("end_turn", [_text_block("first answer")])

    class BlockingClient:
        messages = BlockingMessages()

    service = CodeQuestionService(BlockingClient(), project_dir=project, harness_dir=harness)
    first_done = threading.Event()
    assert service.ask("first", lambda _text: first_done.set()) is True
    assert entered.wait(2)

    busy: list[str] = []
    assert service.ask("second", busy.append) is False
    assert busy and "already" in busy[0]

    too_long: list[str] = []
    assert service.ask("x" * (QUESTION_MAX_CHARS + 1), too_long.append) is False
    assert "maximum 2000" in too_long[0]

    release.set()
    assert first_done.wait(2)


def test_code_question_service_reports_timeout_with_metrics_and_releases_slot(tmp_path):
    project = tmp_path / "project"
    harness = tmp_path / "harness"
    project.mkdir()
    harness.mkdir()
    service = CodeQuestionService(_FakeClient([]), project_dir=project, harness_dir=harness)
    timeout = PhaseTimeout(
        "deadline",
        metrics={
            "turns": 2,
            "elapsed": 120.0,
            "input_tokens": 44,
            "output_tokens": 11,
            "model": service.model,
        },
    )
    delivered: list[str] = []
    done = threading.Event()

    with patch.object(service.runner, "run_phase", side_effect=timeout):
        assert service.ask("Explain the timeout", lambda text: (delivered.append(text), done.set()))
        assert done.wait(2)

    for _ in range(100):
        if not service.is_busy:
            break
        time.sleep(0.001)
    assert service.is_busy is False
    assert "timed out" in delivered[0]
    event = json.loads((harness / "_telemetry.jsonl").read_text(encoding="utf-8"))
    assert event["result"] == "timeout"
    assert event["turns"] == 2
    assert event["cost"]["total_tokens"] == 55


def test_code_question_service_converts_internal_errors_to_safe_response(tmp_path):
    project = tmp_path / "project"
    harness = tmp_path / "harness"
    project.mkdir()
    harness.mkdir()
    service = CodeQuestionService(_FakeClient([]), project_dir=project, harness_dir=harness)
    delivered: list[str] = []
    done = threading.Event()

    with patch.object(service.runner, "run_phase", side_effect=RuntimeError("SECRET_EXCEPTION")):
        assert service.ask("SECRET_QUESTION", lambda text: (delivered.append(text), done.set()))
        assert done.wait(2)

    assert delivered == ["Unable to answer the code question due to an internal error."]
    telemetry = (harness / "_telemetry.jsonl").read_text(encoding="utf-8")
    assert json.loads(telemetry)["result"] == "error"
    assert "SECRET_EXCEPTION" not in telemetry
    assert "SECRET_QUESTION" not in telemetry
