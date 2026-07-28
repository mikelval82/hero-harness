from __future__ import annotations

import time
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Callable

from anthropic import RateLimitError, APITimeoutError, APIConnectionError, APIStatusError

from src.agent.tools import execute_tool
from src.core.model_policy import DEFAULT_MODEL, resolve_model_id

MODEL = DEFAULT_MODEL
MAX_TOKENS = 16384
MAX_TURNS = 50
MAX_TOOL_RESULT = 50000


class AgentError(Exception): ...


class PhaseTimeout(AgentError):
    def __init__(self, msg, metrics=None):
        super().__init__(msg)
        self.metrics = metrics


class MaxTurnsExceeded(AgentError):
    def __init__(self, msg, metrics=None):
        super().__init__(msg)
        self.metrics = metrics


class MaxRetriesExceeded(AgentError):
    def __init__(self, msg, metrics=None):
        super().__init__(msg)
        self.metrics = metrics


class RequestDeadlineExceeded(AgentError):
    """The shared phase deadline expired during API retry handling."""


@dataclass
class PhaseResult:
    text: str
    turns: int
    elapsed: float
    input_tokens: int
    output_tokens: int
    model: str = MODEL


def create_with_retry(
    client,
    *,
    max_retries: int = 3,
    on_log: Optional[Callable[[str], None]] = None,
    deadline: float | None = None,
    **kwargs,
):
    for attempt in range(max_retries + 1):
        call_kwargs = kwargs
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RequestDeadlineExceeded("API request deadline expired")
            call_kwargs = {**kwargs, "timeout": remaining}
        try:
            return client.messages.create(**call_kwargs)
        except (RateLimitError, APITimeoutError, APIConnectionError) as exc:
            if deadline is not None and deadline - time.monotonic() <= 0:
                raise RequestDeadlineExceeded("API request deadline expired") from exc
            if attempt >= max_retries:
                raise MaxRetriesExceeded(f"Exhausted {max_retries} retries: {exc}") from exc
            wait = 2 ** attempt + random.random()
            if deadline is not None and wait >= deadline - time.monotonic():
                raise RequestDeadlineExceeded("API retry would exceed phase deadline") from exc
            if on_log:
                on_log(f"API retry {attempt + 1}/{max_retries}: {type(exc).__name__}, waiting {wait:.0f}s")
            time.sleep(wait)
        except APIStatusError as exc:
            if exc.status_code >= 500:
                if deadline is not None and deadline - time.monotonic() <= 0:
                    raise RequestDeadlineExceeded("API request deadline expired") from exc
                if attempt >= max_retries:
                    raise MaxRetriesExceeded(f"Exhausted {max_retries} retries: {exc}") from exc
                wait = 2 ** attempt
                if deadline is not None and wait >= deadline - time.monotonic():
                    raise RequestDeadlineExceeded("API retry would exceed phase deadline") from exc
                if on_log:
                    on_log(f"API retry {attempt + 1}/{max_retries}: HTTP {exc.status_code}, waiting {wait}s")
                time.sleep(wait)
            else:
                raise


def _extract_text(response) -> str:
    return "".join(b.text for b in response.content if b.type == "text")


DONE_SIGNAL = "__GRILL_DONE__"
ABORT_SIGNAL = "__MISSION_ABORT__"


class AgentRunner:

    def __init__(self, client):
        self.client = client

    def _run_loop(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict],
        phase_name: str,
        project_dir: Path,
        harness_dir: Path,
        on_tool_call: Optional[Callable[[str, dict], None]] = None,
        on_log: Optional[Callable[[str], None]] = None,
        timeout: int,
        max_turns: int = MAX_TURNS,
        max_tokens: int = MAX_TOKENS,
        max_tool_result: int = MAX_TOOL_RESULT,
        allow_project_writes: bool = False,
        get_human_input: Optional[Callable[[str], str]] = None,
        should_stop_after_tools: Optional[Callable[[list], bool]] = None,
        model: str | None = None,
    ) -> PhaseResult:
        start = time.monotonic()
        deadline = start + timeout
        messages = [{"role": "user", "content": user_prompt}]
        total_input_tokens = 0
        total_output_tokens = 0
        interactive = get_human_input is not None
        selected_model = model or resolve_model_id("default")
        if max_tokens < 1:
            raise ValueError("max_tokens must be positive")
        if max_tool_result < 1:
            raise ValueError("max_tool_result must be positive")
        announced_tools = {
            str(tool["name"])
            for tool in tools
            if isinstance(tool, dict) and tool.get("name")
        }

        for turn in range(max_turns):
            elapsed = time.monotonic() - start
            if elapsed >= timeout:
                if on_log:
                    on_log(f"TIMEOUT after {elapsed:.0f}s")
                raise PhaseTimeout(f"{phase_name}: exceeded {timeout}s", metrics={
                    "turns": turn, "elapsed": elapsed,
                    "input_tokens": total_input_tokens, "output_tokens": total_output_tokens,
                    "model": selected_model,
                })

            if on_log:
                on_log(f"Turn {turn + 1}/{max_turns} — calling API...")

            try:
                response = create_with_retry(
                    self.client,
                    model=selected_model,
                    max_tokens=max_tokens,
                    system=system_prompt,
                    tools=tools,
                    messages=messages,
                    on_log=on_log,
                    deadline=deadline,
                )
            except RequestDeadlineExceeded as exc:
                elapsed = time.monotonic() - start
                raise PhaseTimeout(f"{phase_name}: exceeded {timeout}s", metrics={
                    "turns": turn, "elapsed": elapsed,
                    "input_tokens": total_input_tokens, "output_tokens": total_output_tokens,
                    "model": selected_model,
                }) from exc
            except MaxRetriesExceeded as exc:
                raise MaxRetriesExceeded(str(exc), metrics={
                    "turns": turn, "elapsed": time.monotonic() - start,
                    "input_tokens": total_input_tokens, "output_tokens": total_output_tokens,
                    "model": selected_model,
                }) from exc

            total_input_tokens += response.usage.input_tokens
            total_output_tokens += response.usage.output_tokens

            tool_blocks = [b for b in response.content if b.type == "tool_use"]
            text = _extract_text(response)
            if on_log:
                on_log(f"Turn {turn + 1} — {response.stop_reason}, {len(tool_blocks)} tool call(s)")
            if text.strip() and on_log:
                preview = text.strip().replace("\n", " ")[:200]
                on_log(f"  [claude] {preview}")

            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})
                tool_results = []
                executed_tool_blocks = []
                for block in tool_blocks:
                    is_allowed = block.name in announced_tools
                    if not is_allowed:
                        if on_log:
                            on_log(f"Blocked unannounced tool call: {block.name}")
                        result = (
                            f"Error: tool '{block.name}' was not announced for this "
                            "run and was not executed."
                        )
                    else:
                        executed_tool_blocks.append(block)
                        if on_tool_call:
                            on_tool_call(block.name, block.input)
                        tool_input = dict(block.input)
                        tool_input["_timeout_seconds"] = max(
                            0.001,
                            deadline - time.monotonic(),
                        )
                        result = execute_tool(
                            block.name,
                            tool_input,
                            project_dir,
                            harness_dir,
                            allow_project_writes=allow_project_writes,
                        )
                        if time.monotonic() >= deadline:
                            elapsed = time.monotonic() - start
                            raise PhaseTimeout(
                                f"{phase_name}: exceeded {timeout}s",
                                metrics={
                                    "turns": turn + 1,
                                    "elapsed": elapsed,
                                    "input_tokens": total_input_tokens,
                                    "output_tokens": total_output_tokens,
                                    "model": selected_model,
                                },
                            )
                    if len(result) > max_tool_result:
                        result = result[:max_tool_result] + chr(10) + "... [truncated]"
                    tool_result = {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    }
                    if not is_allowed:
                        tool_result["is_error"] = True
                    tool_results.append(tool_result)
                messages.append({"role": "user", "content": tool_results})
                if (
                    should_stop_after_tools
                    and executed_tool_blocks
                    and should_stop_after_tools(executed_tool_blocks)
                ):
                    if on_log:
                        on_log(f"Phase done after {turn + 1} turns ({time.monotonic() - start:.0f}s)")
                    return PhaseResult(text=_extract_text(response), turns=turn + 1,
                                       elapsed=time.monotonic() - start,
                                       input_tokens=total_input_tokens,
                                       output_tokens=total_output_tokens,
                                       model=selected_model)
                continue

            if not interactive or not text.strip():
                elapsed = time.monotonic() - start
                if on_log:
                    on_log(f"Phase done after {turn + 1} turns ({elapsed:.0f}s)")
                return PhaseResult(text=text, turns=turn + 1, elapsed=elapsed,
                                   input_tokens=total_input_tokens, output_tokens=total_output_tokens,
                                   model=selected_model)

            human_reply = get_human_input(text)
            if human_reply == ABORT_SIGNAL:
                elapsed = time.monotonic() - start
                if on_log:
                    on_log(f"Conversation aborted after {turn + 1} turns ({elapsed:.0f}s)")
                return PhaseResult(
                    text=text,
                    turns=turn + 1,
                    elapsed=elapsed,
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                    model=selected_model,
                )
            if human_reply == DONE_SIGNAL:
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": "/done"})
                continue

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": human_reply})

        if on_log:
            on_log(f"MAX TURNS exceeded ({max_turns})")
        raise MaxTurnsExceeded(f"{phase_name}: exceeded {max_turns} turns", metrics={
            "turns": max_turns, "elapsed": time.monotonic() - start,
            "input_tokens": total_input_tokens, "output_tokens": total_output_tokens,
            "model": selected_model,
        })

    def run_conversation(self, *, get_human_input, timeout=1800, **kwargs) -> PhaseResult:
        return self._run_loop(get_human_input=get_human_input, timeout=timeout, **kwargs)

    def run_phase(self, *, timeout=1200, **kwargs) -> PhaseResult:
        return self._run_loop(timeout=timeout, **kwargs)


def run_phase(client, **kwargs) -> PhaseResult:
    return AgentRunner(client).run_phase(**kwargs)


def run_conversation(client, **kwargs) -> PhaseResult:
    return AgentRunner(client).run_conversation(**kwargs)
