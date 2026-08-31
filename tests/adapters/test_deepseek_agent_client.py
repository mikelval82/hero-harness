from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from mission_orchestrator.adapters.deepseek.client import DeepSeekAgentClient
from mission_orchestrator.domain.phase import PhaseAuthority, PhaseName
from mission_orchestrator.ports.agent_client import AgentRequest
from mission_orchestrator.ports.tool_registry import ToolAuthorizationError


class _FakeCompletions:
    def __init__(self, responses: list) -> None:
        self.responses = responses
        self.calls: list[dict] = []

    def create(self, **kwargs):  # noqa: ANN003, ANN201
        self.calls.append(kwargs)
        return self.responses.pop(0)


class _Registry:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def execute(self, name: str, input: dict, env, authority) -> str:  # noqa: A002, ANN001
        del env, authority
        self.calls.append((name, input))
        return "graph result"


def _response(*, text: str = "", tool_calls: list | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=text, tool_calls=tool_calls or [])
            )
        ],
        usage=SimpleNamespace(prompt_tokens=3, completion_tokens=2),
    )


class DeepSeekAgentClientTest(unittest.TestCase):
    def test_runs_openai_compatible_tool_loop(self) -> None:
        tool_call = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(
                name="GraphSearch",
                arguments=json.dumps({"query": "OrderService"}),
            ),
        )
        completions = _FakeCompletions(
            [_response(tool_calls=[tool_call]), _response(text="done")]
        )
        registry = _Registry()
        client = DeepSeekAgentClient.__new__(DeepSeekAgentClient)
        client.tools = registry
        client.tool_env = None
        client.command_bus = None
        client.model = "deepseek-v4-flash"
        client.max_tokens = 256
        client.max_retries = 1
        client.events = SimpleNamespace(publish=lambda kind, payload: None)
        client._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

        result = client.run_phase(
            AgentRequest(
                phase_name="test",
                system_prompt="Use tools.",
                user_prompt="Find the service.",
                tool_names=("GraphSearch",),
                tool_schemas=[
                    {
                        "name": "GraphSearch",
                        "description": "Search nodes",
                        "input_schema": {"type": "object"},
                    }
                ],
                authority=PhaseAuthority(PhaseName.RESEARCH, ("GraphSearch",)),
                max_turns=3,
                timeout_seconds=30,
            )
        )

        self.assertEqual(result.text, "done")
        self.assertEqual(result.turns, 2)
        self.assertEqual(result.input_tokens, 6)
        self.assertEqual(result.output_tokens, 4)
        self.assertEqual(registry.calls, [("GraphSearch", {"query": "OrderService"})])
        first = completions.calls[0]
        self.assertEqual(first["max_tokens"], 256)
        self.assertEqual(first["tools"][0]["function"]["name"], "GraphSearch")
        second_messages = completions.calls[1]["messages"]
        self.assertEqual(second_messages[-1]["role"], "tool")
        self.assertEqual(second_messages[-1]["tool_call_id"], "call-1")

    def test_authorization_rejection_stops_the_provider_loop(self) -> None:
        tool_call = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(name="Edit", arguments=json.dumps({"file_path": "src/app.py"})),
        )
        completions = _FakeCompletions([_response(tool_calls=[tool_call])])

        class DenyingRegistry:
            def execute(self, name, input, env, authority):  # noqa: ANN001
                raise ToolAuthorizationError(authority.phase.value, name, "tool_not_allowed")

        client = DeepSeekAgentClient.__new__(DeepSeekAgentClient)
        client.tools = DenyingRegistry()
        client.tool_env = None
        client.command_bus = None
        client.model = "deepseek-v4-flash"
        client.max_tokens = 256
        client.max_retries = 1
        client.events = SimpleNamespace(publish=lambda kind, payload: None)
        client._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

        with self.assertRaises(ToolAuthorizationError):
            client.run_phase(
                AgentRequest(
                    phase_name="research",
                    system_prompt="Use tools.",
                    user_prompt="Try edit.",
                    tool_names=("Read",),
                    tool_schemas=[],
                    authority=PhaseAuthority(PhaseName.RESEARCH, ("Read",)),
                    max_turns=3,
                    timeout_seconds=30,
                )
            )


if __name__ == "__main__":
    unittest.main()
