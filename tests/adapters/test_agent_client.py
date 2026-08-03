"""Acceptance tests for the Anthropic agent loop tool-error handling.

A tool failure (policy rejection, bad input, runtime error) must be returned
to the model as an ``is_error`` tool_result so it can self-correct, instead of
crashing the phase.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from mission_orchestrator.adapters.anthropic.client import AnthropicAgentClient
from mission_orchestrator.ports.agent_client import AgentRequest


class _FakeBlock(SimpleNamespace):
    pass


def _tool_use(call_id: str, name: str, input: dict) -> _FakeBlock:
    return _FakeBlock(type="tool_use", id=call_id, name=name, input=input)


def _text(text: str) -> _FakeBlock:
    return _FakeBlock(type="text", text=text)


class _FakeMessages:
    def __init__(self, responses: list) -> None:
        self._responses = responses
        self.calls: list[dict] = []

    def create(self, **kwargs) -> SimpleNamespace:
        self.calls.append(kwargs)
        return self._responses.pop(0)


class _FakeRegistry:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def execute(self, name: str, input: dict, env) -> str:
        raise self._error


def _make_client(responses: list, registry) -> AnthropicAgentClient:
    client = AnthropicAgentClient.__new__(AnthropicAgentClient)
    client.tools = registry
    client.tool_env = None
    client.command_bus = None
    client.model = "test-model"
    client.max_tokens = 128
    client.max_retries = 1
    client._client = SimpleNamespace(messages=_FakeMessages(responses))
    return client


def _request() -> AgentRequest:
    return AgentRequest(
        phase_name="test",
        system_prompt="",
        user_prompt="do the thing",
        tool_names=[],
        tool_schemas=[],
        max_turns=5,
        timeout_seconds=30,
    )


class ToolErrorHandlingTest(unittest.TestCase):
    def test_tool_exception_is_returned_as_error_result(self) -> None:
        responses = [
            SimpleNamespace(
                content=[_tool_use("t1", "Bash", {"command": "dir /s"})],
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            ),
            SimpleNamespace(
                content=[_text("recovered")],
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            ),
        ]
        registry = _FakeRegistry(PermissionError("command not allowed: dir"))
        client = _make_client(responses, registry)

        result = client.run_phase(_request())

        self.assertEqual(result.text, "recovered")
        self.assertEqual(result.turns, 2)
        second_call = client._client.messages.calls[1]
        tool_results = second_call["messages"][-1]["content"]
        self.assertEqual(len(tool_results), 1)
        entry = tool_results[0]
        self.assertEqual(entry["tool_use_id"], "t1")
        self.assertTrue(entry["is_error"])
        self.assertIn("command not allowed: dir", entry["content"])

    def test_unknown_tool_is_returned_as_error_result(self) -> None:
        responses = [
            SimpleNamespace(
                content=[_tool_use("t1", "Nope", {})],
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            ),
            SimpleNamespace(
                content=[_text("done")],
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            ),
        ]
        registry = _FakeRegistry(KeyError("unknown tool: Nope"))
        client = _make_client(responses, registry)

        result = client.run_phase(_request())

        self.assertEqual(result.text, "done")
        entry = client._client.messages.calls[1]["messages"][-1]["content"][0]
        self.assertTrue(entry["is_error"])
        self.assertIn("unknown tool", entry["content"])


if __name__ == "__main__":
    unittest.main()
