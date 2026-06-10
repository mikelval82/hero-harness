from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest


def _make_response(stop_reason, content, input_tokens=100, output_tokens=50):
    r = MagicMock()
    r.stop_reason = stop_reason
    r.content = content
    r.usage.input_tokens = input_tokens
    r.usage.output_tokens = output_tokens
    return r


def _text_block(text):
    b = MagicMock()
    b.type = "text"
    b.text = text
    return b


def _tool_block(name, inp, tool_id="tu_1"):
    b = MagicMock()
    b.type = "tool_use"
    b.name = name
    b.input = inp
    b.id = tool_id
    return b


def test_constants():
    from src.agent.loop import MODEL, MAX_TOKENS, MAX_TURNS, MAX_TOOL_RESULT
    assert MODEL == "claude-sonnet-4-6"
    assert MAX_TOKENS == 16384
    assert MAX_TURNS == 50
    assert MAX_TOOL_RESULT == 50000


def test_exception_hierarchy():
    from src.agent.loop import AgentError, PhaseTimeout, MaxTurnsExceeded, MaxRetriesExceeded
    assert issubclass(PhaseTimeout, AgentError)
    assert issubclass(MaxTurnsExceeded, AgentError)
    assert issubclass(MaxRetriesExceeded, AgentError)
    assert issubclass(AgentError, Exception)


def test_create_with_retry_success():
    from src.agent.loop import create_with_retry
    client = MagicMock()
    client.messages.create.return_value = "ok"
    result = create_with_retry(client, model="m", messages=[])
    assert result == "ok"
    client.messages.create.assert_called_once_with(model="m", messages=[])


def test_create_with_retry_rate_limit_then_success():
    from anthropic import RateLimitError
    from src.agent.loop import create_with_retry
    client = MagicMock()
    resp = MagicMock()
    resp.status_code = 429
    resp.headers = {}
    exc = RateLimitError(message="rate limit", response=resp, body=None)
    client.messages.create.side_effect = [exc, "ok"]
    with patch("src.agent.loop.time.sleep"):
        result = create_with_retry(client, max_retries=3, model="m", messages=[])
    assert result == "ok"
    assert client.messages.create.call_count == 2


def test_create_with_retry_timeout_then_success():
    from anthropic import APITimeoutError
    from src.agent.loop import create_with_retry
    client = MagicMock()
    exc = APITimeoutError(request=MagicMock())
    client.messages.create.side_effect = [exc, "ok"]
    with patch("src.agent.loop.time.sleep"):
        result = create_with_retry(client, max_retries=3, model="m", messages=[])
    assert result == "ok"


def test_create_with_retry_connection_then_success():
    from anthropic import APIConnectionError
    from src.agent.loop import create_with_retry
    client = MagicMock()
    exc = APIConnectionError(request=MagicMock())
    client.messages.create.side_effect = [exc, "ok"]
    with patch("src.agent.loop.time.sleep"):
        result = create_with_retry(client, max_retries=3, model="m", messages=[])
    assert result == "ok"


def test_create_with_retry_5xx_then_success():
    from anthropic import APIStatusError
    from src.agent.loop import create_with_retry
    client = MagicMock()
    resp = MagicMock()
    resp.status_code = 500
    resp.headers = {}
    exc = APIStatusError(message="server error", response=resp, body=None)
    client.messages.create.side_effect = [exc, "ok"]
    with patch("src.agent.loop.time.sleep"):
        result = create_with_retry(client, max_retries=3, model="m", messages=[])
    assert result == "ok"


def test_create_with_retry_4xx_reraises():
    from anthropic import APIStatusError
    from src.agent.loop import create_with_retry
    client = MagicMock()
    resp = MagicMock()
    resp.status_code = 400
    resp.headers = {}
    exc = APIStatusError(message="bad request", response=resp, body=None)
    client.messages.create.side_effect = exc
    with pytest.raises(APIStatusError):
        create_with_retry(client, max_retries=3, model="m", messages=[])
    assert client.messages.create.call_count == 1


def test_create_with_retry_exhausted():
    from anthropic import RateLimitError
    from src.agent.loop import create_with_retry, MaxRetriesExceeded
    client = MagicMock()
    resp = MagicMock()
    resp.status_code = 429
    resp.headers = {}
    exc = RateLimitError(message="rate limit", response=resp, body=None)
    client.messages.create.side_effect = exc
    with patch("src.agent.loop.time.sleep"):
        with pytest.raises(MaxRetriesExceeded):
            create_with_retry(client, max_retries=2, model="m", messages=[])
    assert client.messages.create.call_count == 3


def test_create_with_retry_backoff_timing():
    from anthropic import APITimeoutError
    from src.agent.loop import create_with_retry, MaxRetriesExceeded
    client = MagicMock()
    exc = APITimeoutError(request=MagicMock())
    client.messages.create.side_effect = exc
    sleep_calls = []
    with patch("src.agent.loop.time.sleep", side_effect=lambda s: sleep_calls.append(s)):
        with patch("src.agent.loop.random.random", return_value=0.5):
            with pytest.raises(MaxRetriesExceeded):
                create_with_retry(client, max_retries=3, model="m", messages=[])
    assert len(sleep_calls) == 3
    assert sleep_calls[0] == pytest.approx(1.5)
    assert sleep_calls[1] == pytest.approx(2.5)
    assert sleep_calls[2] == pytest.approx(4.5)


def test_extract_text_single_block():
    from src.agent.loop import _extract_text
    response = _make_response("end_turn", [_text_block("hello world")])
    assert _extract_text(response) == "hello world"


def test_extract_text_multiple_blocks():
    from src.agent.loop import _extract_text
    b1 = _text_block("hello ")
    b2 = _text_block("world")
    response = _make_response("end_turn", [b1, b2])
    assert _extract_text(response) == "hello world"


def test_extract_text_mixed_blocks():
    from src.agent.loop import _extract_text
    b1 = _text_block("result")
    b2 = _tool_block("Read", {})
    response = _make_response("end_turn", [b1, b2])
    assert _extract_text(response) == "result"


def test_extract_text_no_text_blocks():
    from src.agent.loop import _extract_text
    response = _make_response("end_turn", [])
    assert _extract_text(response) == ""


def test_run_phase_end_turn_immediate():
    from src.agent.loop import run_phase
    client = MagicMock()
    resp = _make_response("end_turn", [_text_block("done")])
    client.messages.create.return_value = resp
    result = run_phase(
        client, system_prompt="sys", user_prompt="go", tools=[],
        phase_name="test", project_dir=Path("/tmp/proj"),
        harness_dir=Path("/tmp/harness"),
    )
    assert result.text == "done"
    assert result.model == "claude-sonnet-4-6"


def test_run_phase_max_tokens_treated_as_end():
    from src.agent.loop import run_phase
    client = MagicMock()
    resp = _make_response("max_tokens", [_text_block("partial")])
    client.messages.create.return_value = resp
    result = run_phase(
        client, system_prompt="sys", user_prompt="go", tools=[],
        phase_name="test", project_dir=Path("/tmp/proj"),
        harness_dir=Path("/tmp/harness"),
    )
    assert result.text == "partial"


def test_run_phase_tool_then_end():
    from src.agent.loop import run_phase
    client = MagicMock()
    tool_resp = _make_response("tool_use", [_tool_block("Read", {"file_path": "/f"})])
    end_resp = _make_response("end_turn", [_text_block("all done")])
    client.messages.create.side_effect = [tool_resp, end_resp]
    with patch("src.agent.loop.execute_tool", return_value="file contents"):
        result = run_phase(
            client, system_prompt="sys", user_prompt="go",
            tools=[{"name": "Read"}], phase_name="test",
            project_dir=Path("/tmp/proj"), harness_dir=Path("/tmp/harness"),
        )
    assert result.text == "all done"
    assert client.messages.create.call_count == 2


def test_run_phase_uses_explicit_model():
    from src.agent.loop import run_phase
    client = MagicMock()
    resp = _make_response("end_turn", [_text_block("done")])
    client.messages.create.return_value = resp
    result = run_phase(
        client, system_prompt="sys", user_prompt="go", tools=[],
        phase_name="test", project_dir=Path("/tmp/proj"),
        harness_dir=Path("/tmp/harness"), model="claude-haiku-4-5",
    )
    assert result.model == "claude-haiku-4-5"
    assert client.messages.create.call_args[1]["model"] == "claude-haiku-4-5"


def test_run_phase_tool_result_message_structure():
    from src.agent.loop import run_phase
    client = MagicMock()
    tb = _tool_block("Read", {"file_path": "/f"}, tool_id="tu_abc")
    tool_resp = _make_response("tool_use", [tb])
    end_resp = _make_response("end_turn", [_text_block("ok")])
    client.messages.create.side_effect = [tool_resp, end_resp]
    with patch("src.agent.loop.execute_tool", return_value="data"):
        run_phase(
            client, system_prompt="sys", user_prompt="go", tools=[],
            phase_name="test", project_dir=Path("/tmp/proj"),
            harness_dir=Path("/tmp/harness"),
        )
    second_call_msgs = client.messages.create.call_args_list[1][1]["messages"]
    tool_result_msg = second_call_msgs[-1]
    assert tool_result_msg["role"] == "user"
    assert tool_result_msg["content"][0]["type"] == "tool_result"
    assert tool_result_msg["content"][0]["tool_use_id"] == "tu_abc"
    assert tool_result_msg["content"][0]["content"] == "data"


def test_run_phase_on_tool_call_invoked():
    from src.agent.loop import run_phase
    client = MagicMock()
    tb = _tool_block("Bash", {"command": "ls"}, tool_id="tu_2")
    tool_resp = _make_response("tool_use", [tb])
    end_resp = _make_response("end_turn", [_text_block("ok")])
    client.messages.create.side_effect = [tool_resp, end_resp]
    callback = MagicMock()
    with patch("src.agent.loop.execute_tool", return_value="output"):
        run_phase(
            client, system_prompt="sys", user_prompt="go", tools=[],
            phase_name="test", project_dir=Path("/tmp/proj"),
            harness_dir=Path("/tmp/harness"), on_tool_call=callback,
        )
    callback.assert_called_once_with("Bash", {"command": "ls"})


def test_run_phase_no_callback_ok():
    from src.agent.loop import run_phase
    client = MagicMock()
    tb = _tool_block("Read", {"file_path": "/f"}, tool_id="tu_3")
    tool_resp = _make_response("tool_use", [tb])
    end_resp = _make_response("end_turn", [_text_block("ok")])
    client.messages.create.side_effect = [tool_resp, end_resp]
    with patch("src.agent.loop.execute_tool", return_value="ok"):
        result = run_phase(
            client, system_prompt="sys", user_prompt="go", tools=[],
            phase_name="test", project_dir=Path("/tmp/proj"),
            harness_dir=Path("/tmp/harness"),
        )
    assert result.text == "ok"


def test_run_phase_truncates_large_tool_result():
    from src.agent.loop import run_phase, MAX_TOOL_RESULT
    client = MagicMock()
    tb = _tool_block("Read", {"file_path": "/big"}, tool_id="tu_4")
    tool_resp = _make_response("tool_use", [tb])
    end_resp = _make_response("end_turn", [_text_block("ok")])
    client.messages.create.side_effect = [tool_resp, end_resp]
    big_result = "x" * (MAX_TOOL_RESULT + 1000)
    with patch("src.agent.loop.execute_tool", return_value=big_result):
        run_phase(
            client, system_prompt="sys", user_prompt="go", tools=[],
            phase_name="test", project_dir=Path("/tmp/proj"),
            harness_dir=Path("/tmp/harness"),
        )
    second_call_msgs = client.messages.create.call_args_list[1][1]["messages"]
    tool_content = second_call_msgs[-1]["content"][0]["content"]
    suffix = chr(10) + "... [truncated]"
    assert len(tool_content) == MAX_TOOL_RESULT + len(suffix)
    assert tool_content.endswith(suffix)


def test_run_phase_timeout():
    from src.agent.loop import run_phase, PhaseTimeout
    client = MagicMock()
    mono_values = [0.0, 1201.0]
    with patch("src.agent.loop.time.monotonic", side_effect=mono_values):
        with pytest.raises(PhaseTimeout, match="test_phase.*1200"):
            run_phase(
                client, system_prompt="sys", user_prompt="go", tools=[],
                phase_name="test_phase", project_dir=Path("/tmp/proj"),
                harness_dir=Path("/tmp/harness"), timeout=1200,
            )


def test_run_phase_max_turns():
    from src.agent.loop import run_phase, MaxTurnsExceeded, MAX_TURNS
    client = MagicMock()
    tb = _tool_block("Read", {"file_path": "/f"})
    tool_resp = _make_response("tool_use", [tb])
    client.messages.create.return_value = tool_resp
    with patch("src.agent.loop.execute_tool", return_value="ok"):
        with pytest.raises(MaxTurnsExceeded, match=str(MAX_TURNS)):
            run_phase(
                client, system_prompt="sys", user_prompt="go", tools=[],
                phase_name="test", project_dir=Path("/tmp/proj"),
                harness_dir=Path("/tmp/harness"),
            )
    assert client.messages.create.call_count == MAX_TURNS


def test_no_side_effects_on_import():
    import importlib
    import src.agent.loop as _mod
    old_classes = (_mod.PhaseTimeout, _mod.MaxTurnsExceeded, _mod.MaxRetriesExceeded)
    importlib.reload(_mod)
    _mod.PhaseTimeout, _mod.MaxTurnsExceeded, _mod.MaxRetriesExceeded = old_classes


def test_run_conversation_respects_max_turns():
    from src.agent.loop import run_conversation, MaxTurnsExceeded
    client = MagicMock()
    tb = _tool_block("Read", {"file_path": "/f"})
    tool_resp = _make_response("tool_use", [tb])
    client.messages.create.return_value = tool_resp
    with patch("src.agent.loop.execute_tool", return_value="ok"):
        with pytest.raises(MaxTurnsExceeded, match="3"):
            run_conversation(
                client, system_prompt="sys", user_prompt="go", tools=[],
                phase_name="test", project_dir=Path("/tmp/proj"),
                harness_dir=Path("/tmp/harness"),
                get_human_input=lambda text: "continue",
                max_turns=3,
            )
    assert client.messages.create.call_count == 3


def test_run_phase_multiple_tool_blocks():
    from src.agent.loop import run_phase
    client = MagicMock()
    tb1 = _tool_block("Read", {"file_path": "/a"}, tool_id="tu_a")
    tb2 = _tool_block("Glob", {"pattern": "*.py"}, tool_id="tu_b")
    tool_resp = _make_response("tool_use", [tb1, tb2])
    end_resp = _make_response("end_turn", [_text_block("done")])
    client.messages.create.side_effect = [tool_resp, end_resp]
    call_log = []
    def mock_execute(name, inp, project_dir, harness_dir):
        call_log.append(name)
        return "result_" + name
    with patch("src.agent.loop.execute_tool", side_effect=mock_execute):
        result = run_phase(
            client, system_prompt="sys", user_prompt="go", tools=[],
            phase_name="test", project_dir=Path("/tmp/proj"),
            harness_dir=Path("/tmp/harness"),
        )
    assert result.text == "done"
    assert call_log == ["Read", "Glob"]
    second_call_msgs = client.messages.create.call_args_list[1][1]["messages"]
    tool_results = second_call_msgs[-1]["content"]
    assert len(tool_results) == 2
    assert tool_results[0]["tool_use_id"] == "tu_a"
    assert tool_results[1]["tool_use_id"] == "tu_b"


def test_run_phase_empty_response():
    from src.agent.loop import run_phase
    client = MagicMock()
    resp = _make_response("end_turn", [])
    client.messages.create.return_value = resp
    result = run_phase(
        client, system_prompt="sys", user_prompt="go", tools=[],
        phase_name="test", project_dir=Path("/tmp/proj"),
        harness_dir=Path("/tmp/harness"),
    )
    assert result.text == ""


def test_run_phase_accumulates_tokens():
    from src.agent.loop import run_phase
    client = MagicMock()
    tb = _tool_block("Read", {"file_path": "/f"})
    tool_resp = _make_response("tool_use", [tb], input_tokens=200, output_tokens=80)
    end_resp = _make_response("end_turn", [_text_block("ok")], input_tokens=300, output_tokens=120)
    client.messages.create.side_effect = [tool_resp, end_resp]
    with patch("src.agent.loop.execute_tool", return_value="data"):
        result = run_phase(
            client, system_prompt="sys", user_prompt="go", tools=[],
            phase_name="test", project_dir=Path("/tmp/proj"),
            harness_dir=Path("/tmp/harness"),
        )
    assert result.text == "ok"
    assert result.input_tokens == 500
    assert result.output_tokens == 200
    assert result.turns == 2


def test_run_phase_exception_carries_metrics():
    from src.agent.loop import run_phase, MaxTurnsExceeded
    client = MagicMock()
    tb = _tool_block("Read", {"file_path": "/f"})
    tool_resp = _make_response("tool_use", [tb], input_tokens=150, output_tokens=60)
    client.messages.create.return_value = tool_resp
    with patch("src.agent.loop.execute_tool", return_value="ok"):
        with pytest.raises(MaxTurnsExceeded) as exc_info:
            run_phase(
                client, system_prompt="sys", user_prompt="go", tools=[],
                phase_name="test", project_dir=Path("/tmp/proj"),
                harness_dir=Path("/tmp/harness"), max_turns=3,
            )
    m = exc_info.value.metrics
    assert m["turns"] == 3
    assert m["input_tokens"] == 450
    assert m["output_tokens"] == 180
    assert m["model"] == "claude-sonnet-4-6"
    assert "elapsed" in m


class TestAgentRunner:
    def test_run_phase_happy_path(self):
        from src.agent.loop import AgentRunner
        client = MagicMock()
        end_resp = _make_response("end_turn", [_text_block("done")])
        client.messages.create.return_value = end_resp
        runner = AgentRunner(client)
        result = runner.run_phase(
            system_prompt="sys", user_prompt="go", tools=[],
            phase_name="test", project_dir=Path("/tmp/proj"),
            harness_dir=Path("/tmp/harness"),
        )
        assert result.text == "done"
        assert result.turns == 1

    def test_run_phase_with_tools(self):
        from src.agent.loop import AgentRunner
        client = MagicMock()
        tb = _tool_block("Read", {"file_path": "/f"})
        tool_resp = _make_response("tool_use", [tb])
        end_resp = _make_response("end_turn", [_text_block("ok")])
        client.messages.create.side_effect = [tool_resp, end_resp]
        runner = AgentRunner(client)
        with patch("src.agent.loop.execute_tool", return_value="data"):
            result = runner.run_phase(
                system_prompt="sys", user_prompt="go", tools=[],
                phase_name="test", project_dir=Path("/tmp/proj"),
                harness_dir=Path("/tmp/harness"),
            )
        assert result.turns == 2

    def test_wrapper_matches_class(self):
        from src.agent.loop import AgentRunner, run_phase
        client = MagicMock()
        end_resp = _make_response("end_turn", [_text_block("x")])
        client.messages.create.return_value = end_resp
        kwargs = dict(system_prompt="s", user_prompt="u", tools=[],
                      phase_name="t", project_dir=Path("/tmp/p"),
                      harness_dir=Path("/tmp/h"))
        r1 = AgentRunner(client).run_phase(**kwargs)
        client.messages.create.return_value = end_resp
        r2 = run_phase(client, **kwargs)
        assert r1.text == r2.text


def test_run_conversation_tool_stop_condition_exits(tmp_path):
    from src.agent.loop import run_conversation
    client = MagicMock()
    harness = tmp_path / "harness"
    harness.mkdir()
    tb = _tool_block("Write", {"file_path": str(harness / "artifact.md")}, tool_id="tu_artifact")
    tool_resp = _make_response("tool_use", [tb])
    client.messages.create.return_value = tool_resp
    with patch("src.agent.loop.execute_tool", return_value="ok"):
        result = run_conversation(
            client, system_prompt="sys", user_prompt="go", tools=[],
            phase_name="grill", project_dir=tmp_path / "proj",
            harness_dir=harness,
            get_human_input=lambda text: "continue",
            should_stop_after_tools=lambda blocks: blocks[0].name == "Write",
        )
    assert result.turns == 1
    assert client.messages.create.call_count == 1


def test_run_conversation_without_tool_stop_condition_continues(tmp_path):
    from src.agent.loop import run_conversation
    client = MagicMock()
    harness = tmp_path / "harness"
    harness.mkdir()
    tb = _tool_block("Write", {"file_path": str(harness / "artifact.md")}, tool_id="tu_artifact")
    tool_resp = _make_response("tool_use", [tb])
    end_resp = _make_response("end_turn", [])
    client.messages.create.side_effect = [tool_resp, end_resp]
    with patch("src.agent.loop.execute_tool", return_value="ok"):
        result = run_conversation(
            client, system_prompt="sys", user_prompt="go", tools=[],
            phase_name="grill", project_dir=tmp_path / "proj",
            harness_dir=harness,
            get_human_input=lambda text: "continue",
    )
    assert result.turns == 2
    assert result.text == ""


def test_run_phase_ignores_tool_stop_condition_by_default(tmp_path):
    from src.agent.loop import run_phase
    client = MagicMock()
    harness = tmp_path / "harness"
    harness.mkdir()
    tb = _tool_block("Write", {"file_path": str(harness / "artifact.md")}, tool_id="tu_artifact")
    tool_resp = _make_response("tool_use", [tb])
    end_resp = _make_response("end_turn", [_text_block("finished")])
    client.messages.create.side_effect = [tool_resp, end_resp]
    with patch("src.agent.loop.execute_tool", return_value="ok"):
        result = run_phase(
            client, system_prompt="sys", user_prompt="go", tools=[],
            phase_name="test", project_dir=tmp_path / "proj",
            harness_dir=harness,
        )
    assert result.turns == 2
    assert result.text == "finished"


def test_agent_loop_has_no_brief_artifact_coupling():
    source = Path("src/agent/loop.py").read_text(encoding="utf-8")
    assert "brief.md" not in source
