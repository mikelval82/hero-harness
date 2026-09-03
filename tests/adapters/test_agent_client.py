"""Acceptance tests for Anthropic tool errors and terminal authorization rejection."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from mission_orchestrator.adapters.anthropic.client import AnthropicAgentClient
from mission_orchestrator.application.errors import ApiUsageLimitExceeded
from mission_orchestrator.domain.phase import PhaseAuthority, PhaseName
from mission_orchestrator.domain.provider_outcome import ProviderOutcomeError
from mission_orchestrator.ports.agent_client import AgentRequest
from mission_orchestrator.ports.tool_registry import ToolAuthorizationError


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


class _FailingMessages:
    def create(self, **kwargs) -> SimpleNamespace:
        raise RuntimeError("You have reached your specified API usage limits")


class _FakeRegistry:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def execute(self, name: str, input: dict, env, authority) -> str:
        raise self._error


def _make_client(responses: list, registry) -> AnthropicAgentClient:
    client = AnthropicAgentClient.__new__(AnthropicAgentClient)
    client.tools = registry
    client.tool_env = None
    client.command_bus = None
    client.model = "test-model"
    client.max_tokens = 128
    client.max_retries = 1
    client.events = SimpleNamespace(published=[], publish=lambda kind, payload: client.events.published.append((kind, payload)))
    client._client = SimpleNamespace(messages=_FakeMessages(responses))
    return client


def _request() -> AgentRequest:
    return AgentRequest(
        phase_name="test",
        system_prompt="",
        user_prompt="do the thing",
        tool_names=[],
        tool_schemas=[],
        authority=PhaseAuthority(PhaseName.RESEARCH, ()),
        max_turns=5,
        timeout_seconds=30,
    )


class ToolErrorHandlingTest(unittest.TestCase):
    def test_usage_limit_preserves_accumulated_metrics(self) -> None:
        client = _make_client([], _FakeRegistry(KeyError("unused")))
        client._client = SimpleNamespace(messages=_FailingMessages())

        with self.assertRaises(ApiUsageLimitExceeded) as raised:
            client.run_phase(_request())

        self.assertEqual(raised.exception.metrics.turns, 0)
        self.assertEqual(raised.exception.metrics.input_tokens, 0)

    def test_tool_exception_is_returned_as_error_result(self) -> None:
        responses = [
            SimpleNamespace(
                content=[_tool_use("t1", "Bash", {"command": "dir /s"})],
                stop_reason="tool_use",
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            ),
            SimpleNamespace(
                content=[_text("recovered")],
                stop_reason="end_turn",
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            ),
        ]
        registry = _FakeRegistry(PermissionError("command not allowed: dir"))
        client = _make_client(responses, registry)

        result = client.run_phase(_request())

        self.assertEqual(result.text, "recovered")
        self.assertEqual(result.turns, 2)
        progress = [payload for kind, payload in client.events.published if kind == "agent_progress"]
        self.assertEqual(progress[-1]["turn"], 2)
        self.assertEqual(progress[-1]["input_tokens"], 2)
        self.assertEqual(progress[-1]["output_tokens"], 2)
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
                stop_reason="tool_use",
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            ),
            SimpleNamespace(
                content=[_text("done")],
                stop_reason="end_turn",
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

    def test_authorization_rejection_stops_the_provider_loop(self) -> None:
        responses = [
            SimpleNamespace(
                content=[_tool_use("t1", "Edit", {"file_path": "src/app.py"})],
                stop_reason="tool_use",
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            )
        ]
        client = _make_client(
            responses,
            _FakeRegistry(ToolAuthorizationError("research", "Edit", "tool_not_allowed")),
        )

        with self.assertRaises(ToolAuthorizationError):
            client.run_phase(_request())

    def test_path_authorization_rejection_is_returned_for_correction(self) -> None:
        responses = [
            SimpleNamespace(
                content=[_tool_use("t1", "Write", {"file_path": "plan.md"})],
                stop_reason="tool_use",
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            ),
            SimpleNamespace(
                content=[_text("corrected")],
                stop_reason="end_turn",
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            ),
        ]
        client = _make_client(
            responses,
            _FakeRegistry(
                ToolAuthorizationError("spec", "Write", "harness_artifact_not_allowed")
            ),
        )

        result = client.run_phase(_request())

        self.assertEqual(result.text, "corrected")
        entry = client._client.messages.calls[1]["messages"][-1]["content"][0]
        self.assertTrue(entry["is_error"])
        self.assertIn("write was not performed", entry["content"])

    def test_truncated_response_is_rejected(self) -> None:
        client = _make_client([SimpleNamespace(content=[_text("partial")], stop_reason="max_tokens", usage=SimpleNamespace(input_tokens=1, output_tokens=1))], _FakeRegistry(KeyError("unused")))
        with self.assertRaisesRegex(ProviderOutcomeError, "max_tokens"):
            client.run_phase(_request())


if __name__ == "__main__":
    unittest.main()
