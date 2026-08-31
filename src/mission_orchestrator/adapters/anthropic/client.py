from __future__ import annotations

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
class AnthropicAgentClient:
    tools: ToolRegistry
    tool_env: ToolEnvironment
    command_bus: CommandBus | None = None
    model: str = "claude-opus-4-6"
    max_tokens: int = 16_384
    max_retries: int = 3
    conversation: ConversationLog = field(default_factory=NullConversationLog)
    events: EventPublisher = field(default_factory=NullEventPublisher)

    def __post_init__(self) -> None:
        try:
            from anthropic import Anthropic  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "Anthropic SDK is not installed. Install with `uv pip install -e .[anthropic]`."
            ) from exc
        self._client = Anthropic()

    def run_phase(self, request: AgentRequest) -> PhaseResult:
        return self._run(request, interactive=False)

    def run_conversation(self, request: ConversationRequest) -> PhaseResult:
        return self._run(request, interactive=True)

    def _run(self, request: AgentRequest, *, interactive: bool) -> PhaseResult:
        messages: list[dict] = [{"role": "user", "content": request.user_prompt}]
        started = monotonic()
        input_tokens = 0
        output_tokens = 0
        last_text = ""
        for turn in range(1, request.max_turns + 1):
            if monotonic() - started > request.timeout_seconds:
                raise PhaseTimeout("phase timed out", self._metrics(last_text, turn, started, input_tokens, output_tokens))
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
            input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
            output_tokens += int(getattr(usage, "output_tokens", 0) or 0)
            self.events.publish(
                "agent_progress",
                {
                    "phase": request.phase_name,
                    "turn": turn,
                    "max_turns": request.max_turns,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "elapsed_seconds": round(monotonic() - started, 3),
                },
            )
            assistant_content, tool_calls, text = self._normalize_content(response.content)
            last_text = text or last_text
            if tool_calls:
                messages.append({"role": "assistant", "content": assistant_content})
                tool_results = []
                for call in tool_calls:
                    is_error = False
                    try:
                        result = self.tools.execute(
                            call["name"], call["input"], self.tool_env, request.authority
                        )
                    except ToolAuthorizationError:
                        raise
                    except Exception as exc:
                        is_error = True
                        result = f"{exc.__class__.__name__}: {exc}"
                    if len(result) > MAX_TOOL_RESULT_CHARS:
                        result = result[:MAX_TOOL_RESULT_CHARS] + "\n...[truncated]"
                    entry = {
                        "type": "tool_result",
                        "tool_use_id": call["id"],
                        "content": result,
                    }
                    if is_error:
                        entry["is_error"] = True
                    tool_results.append(entry)
                messages.append({"role": "user", "content": tool_results})
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
            messages.append({"role": "assistant", "content": assistant_content})
            messages.append({"role": "user", "content": human})
        raise MaxTurnsExceeded(
            "maximum turns exceeded",
            self._metrics(last_text, request.max_turns, started, input_tokens, output_tokens),
        )

    def _create_with_retries(self, request: AgentRequest, messages: list[dict]):
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                return self._client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    system=request.system_prompt or None,
                    messages=messages,
                    tools=request.tool_schemas,
                )
            except Exception as exc:
                last_exc = exc
                if not self._should_retry(exc):
                    raise
                time.sleep((2**attempt) + random.random())
        raise MaxRetriesExceeded(f"API retries exhausted: {last_exc}") from last_exc

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
        return "usage limit" in message or "usage limits" in message

    @staticmethod
    def _normalize_content(content) -> tuple[list[dict], list[dict], str]:
        assistant_content: list[dict] = []
        tool_calls: list[dict] = []
        texts: list[str] = []
        for block in content:
            block_type = getattr(block, "type", "")
            if block_type == "text":
                text = getattr(block, "text", "")
                assistant_content.append({"type": "text", "text": text})
                texts.append(text)
            elif block_type == "tool_use":
                call = {
                    "type": "tool_use",
                    "id": getattr(block, "id"),
                    "name": getattr(block, "name"),
                    "input": getattr(block, "input", {}),
                }
                assistant_content.append(call)
                tool_calls.append(call)
        return assistant_content, tool_calls, "\n".join(texts).strip()

    def _human_reply(self, agent_text: str) -> str | None:
        if self.command_bus is None:
            return None
        while True:
            command = self.command_bus.get(timeout_seconds=5.0)
            if command is None:
                continue
            if command.kind == CommandKind.ANSWER:
                return command.text
            if command.kind == CommandKind.DONE:
                return None
            if command.kind == CommandKind.ABORT:
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
