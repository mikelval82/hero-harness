from __future__ import annotations

import json
import os
import random
import time
from dataclasses import dataclass, field
from time import monotonic

from mission_orchestrator.application.errors import (
    ApiUsageLimitExceeded,
    MaxRetriesExceeded,
    MaxTurnsExceeded,
    PhaseTimeout,
)
from mission_orchestrator.domain.command import CommandKind
from mission_orchestrator.domain.provider_outcome import ProviderOutcomeError
from mission_orchestrator.domain.conversation import ConversationRole
from mission_orchestrator.domain.phase import PhaseResult
from mission_orchestrator.ports.agent_client import AgentRequest, ConversationRequest
from mission_orchestrator.ports.command_bus import CommandBus
from mission_orchestrator.ports.conversation import ConversationLog, NullConversationLog
from mission_orchestrator.ports.events import EventPublisher, NullEventPublisher
from mission_orchestrator.ports.tool_registry import (
    ToolAuthorizationError,
    ToolEnvironment,
    ToolRegistry,
)


MAX_TOOL_RESULT_CHARS = 50_000


@dataclass
class DeepSeekAgentClient:
    tools: ToolRegistry
    tool_env: ToolEnvironment
    command_bus: CommandBus | None = None
    model: str = "deepseek-v4-flash"
    max_tokens: int = 16_384
    max_retries: int = 3
    conversation: ConversationLog = field(default_factory=NullConversationLog)
    events: EventPublisher = field(default_factory=NullEventPublisher)

    def __post_init__(self) -> None:
        try:
            from openai import OpenAI  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "OpenAI-compatible SDK is not installed. Install with "
                "`uv pip install -e .[deepseek]`."
            ) from exc
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is required to use the DeepSeek provider.")
        self._client = OpenAI(
            api_key=api_key,
            base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        )

    def run_phase(self, request: AgentRequest) -> PhaseResult:
        return self._run(request, interactive=False)

    def run_conversation(self, request: ConversationRequest) -> PhaseResult:
        return self._run(request, interactive=True)

    def _run(self, request: AgentRequest, *, interactive: bool) -> PhaseResult:
        messages: list[dict] = [
            {"role": "system", "content": request.system_prompt},
            {"role": "user", "content": request.user_prompt},
        ]
        started = monotonic()
        input_tokens = 0
        output_tokens = 0
        last_text = ""
        for turn in range(1, request.max_turns + 1):
            if monotonic() - started > request.timeout_seconds:
                raise PhaseTimeout(
                    "phase timed out",
                    self._metrics(last_text, turn, started, input_tokens, output_tokens),
                )
            try:
                response = self._create_with_retries(request, messages)
            except Exception as exc:
                if self._is_usage_limit(exc):
                    raise ApiUsageLimitExceeded(
                        str(exc),
                        self._metrics(last_text, turn - 1, started, input_tokens, output_tokens),
                    ) from exc
                raise
            usage = getattr(response, "usage", None)
            input_tokens += int(getattr(usage, "prompt_tokens", 0) or 0)
            output_tokens += int(getattr(usage, "completion_tokens", 0) or 0)
            self.events.publish(
                "agent_progress",
                {
                    "phase": request.phase_name,
                    "turn": turn,
                    "max_turns": request.max_turns,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "elapsed_seconds": round(monotonic() - started, 3),
                    "requested_model": self.model,
                    "served_model": str(getattr(response, "model", "") or "unknown"),
                },
            )
            if not getattr(response, "choices", None):
                raise ProviderOutcomeError("malformed DeepSeek response: missing choices")
            choice = response.choices[0]
            assistant_message, tool_calls, text = self._normalize_message(choice.message)
            finish_reason = str(getattr(choice, "finish_reason", "") or "")
            expected = "tool_calls" if tool_calls else "stop"
            # A length-limited response may still contain a usable (or
            # recoverably malformed) tool call.  Process it so the tool
            # result can tell the model to repair the truncated arguments.
            accepted_truncated_tools = finish_reason == "length" and bool(tool_calls)
            if finish_reason == "length" and not tool_calls:
                # A phase can hit the output limit while composing the next
                # tool call or artifact instructions. Preserve the partial
                # assistant turn and ask DeepSeek to continue in the same
                # conversation; rejecting it here loses recoverable context.
                if assistant_message.get("content"):
                    messages.append(assistant_message)
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Your previous response was truncated by the output limit. "
                            "Continue from exactly where it stopped, do not repeat completed "
                            "work, and use the available tools to finish the requested phase."
                        ),
                    }
                )
                last_text = text or last_text
                continue
            if finish_reason != expected and not accepted_truncated_tools:
                raise ProviderOutcomeError(f"unaccepted DeepSeek outcome: {finish_reason or 'missing finish_reason'}")
            last_text = text or last_text
            if tool_calls:
                messages.append(assistant_message)
                for call in tool_calls:
                    is_error = False
                    try:
                        if call.get("error"):
                            raise ValueError(call["error"])
                        result = self.tools.execute(
                            call["name"], call["input"], self.tool_env, request.authority
                        )
                    except ToolAuthorizationError as exc:
                        if not exc.recoverable:
                            raise
                        is_error = True
                        result = (
                            f"{exc}. The write was not performed. Correct the file_path "
                            "to the exact project or harness path authorized by this phase."
                        )
                    except Exception as exc:
                        is_error = True
                        result = f"{exc.__class__.__name__}: {exc}"
                    if len(result) > MAX_TOOL_RESULT_CHARS:
                        result = result[:MAX_TOOL_RESULT_CHARS] + "\n...[truncated]"
                    if is_error:
                        result = f"ERROR: {result}"
                    messages.append(
                        {"role": "tool", "tool_call_id": call["id"], "content": result}
                    )
                continue
            if not interactive:
                return self._metrics(last_text, turn, started, input_tokens, output_tokens)
            if text:
                self._record_message(ConversationRole.AGENT, text, request.phase_name)
            human = self._human_reply(last_text)
            if human is None:
                self.events.publish("conversation_closed", {"phase": request.phase_name})
                return self._metrics(last_text, turn, started, input_tokens, output_tokens)
            self._record_message(ConversationRole.HUMAN, human, request.phase_name)
            messages.append(assistant_message)
            messages.append({"role": "user", "content": human})
        raise MaxTurnsExceeded(
            "maximum turns exceeded",
            self._metrics(last_text, request.max_turns, started, input_tokens, output_tokens),
        )

    def _create_with_retries(self, request: AgentRequest, messages: list[dict]):
        last_exc: Exception | None = None
        tools = [
            {
                "type": "function",
                "function": {
                    "name": schema["name"],
                    "description": schema.get("description", ""),
                    "parameters": schema.get("input_schema", {"type": "object"}),
                },
            }
            for schema in request.tool_schemas
        ]
        for attempt in range(self.max_retries):
            try:
                parameters = {
                    "model": self.model,
                    "max_tokens": self.max_tokens,
                    "messages": messages,
                }
                if tools:
                    parameters["tools"] = tools
                return self._client.chat.completions.create(**parameters)
            except Exception as exc:
                last_exc = exc
                if not self._should_retry(exc):
                    raise
                time.sleep((2**attempt) + random.random())
        raise MaxRetriesExceeded(f"API retries exhausted: {last_exc}") from last_exc

    @staticmethod
    def _normalize_message(message) -> tuple[dict, list[dict], str]:
        text = str(getattr(message, "content", "") or "").strip()
        calls: list[dict] = []
        serialized_calls: list[dict] = []
        for tool_call in getattr(message, "tool_calls", None) or []:
            raw_arguments = tool_call.function.arguments or "{}"
            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError as exc:
                # DeepSeek may occasionally emit a truncated tool-call payload.
                # Feed the error back to the model so it can correct the call.
                arguments = {}
                calls.append({"id": tool_call.id, "name": tool_call.function.name,
                              "input": arguments, "error":
                              f"Invalid JSON in tool arguments: {exc.msg} at character {exc.pos}. "
                              f"Received: {raw_arguments[:500]}"})
                serialized_calls.append({"id": tool_call.id, "type": "function",
                                         "function": {"name": tool_call.function.name,
                                                       "arguments": raw_arguments}})
                continue
            calls.append(
                {"id": tool_call.id, "name": tool_call.function.name, "input": arguments}
            )
            serialized_calls.append(
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": raw_arguments,
                    },
                }
            )
        assistant: dict = {"role": "assistant", "content": text or None}
        if serialized_calls:
            assistant["tool_calls"] = serialized_calls
        return assistant, calls, text

    @staticmethod
    def _should_retry(exc: Exception) -> bool:
        name = exc.__class__.__name__.lower()
        if "ratelimit" in name or "timeout" in name or "connection" in name:
            return True
        status = getattr(exc, "status_code", None)
        if isinstance(status, int):
            return status >= 500
        return "internalserver" in name

    @staticmethod
    def _is_usage_limit(exc: Exception) -> bool:
        message = str(exc).lower()
        return any(
            marker in message
            for marker in ("usage limit", "usage limits", "insufficient balance")
        )

    def _human_reply(self, agent_text: str) -> str | None:
        del agent_text
        if self.command_bus is None:
            return None
        while True:
            command = self.command_bus.get(timeout_seconds=5.0)
            if command is None:
                continue
            if command.kind == CommandKind.ANSWER:
                return command.text
            if command.kind in (CommandKind.DONE, CommandKind.ABORT):
                return None
            self.command_bus.defer([command])

    def _record_message(self, role: ConversationRole, content: str, phase: str) -> None:
        message = self.conversation.append(role, content, phase=phase)
        self.events.publish("conversation_message", message.to_json())

    @staticmethod
    def _metrics(
        text: str,
        turns: int,
        started: float,
        input_tokens: int,
        output_tokens: int,
    ) -> PhaseResult:
        return PhaseResult(
            text=text,
            turns=turns,
            elapsed_seconds=round(monotonic() - started, 3),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
