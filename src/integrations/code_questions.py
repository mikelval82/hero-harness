from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Callable, Optional

from src.agent.loop import (
    AgentRunner,
    MaxRetriesExceeded,
    MaxTurnsExceeded,
    PhaseResult,
    PhaseTimeout,
)
from src.agent.tool_schema import TOOL_REGISTRY
from src.core.model_policy import resolve_model_id
from src.harness.telemetry import write_phase_event


QUESTION_MAX_CHARS = 2_000
ANSWER_MAX_CHARS = 3_500
ASK_MAX_TURNS = 8
ASK_TIMEOUT_SECONDS = 120
ASK_MAX_TOKENS = 1_200
ASK_MAX_TOOL_RESULT = 12_000
ASK_TOOL_NAMES = ("Read", "Glob", "Grep", "CodeGraph")


def _short(value: object, limit: int = 300) -> str:
    return str(value or "").replace("\r", " ").replace("\n", " ")[:limit]


class CodeQuestionService:
    """Run one read-only code question at a time on the existing agent loop."""

    def __init__(
        self,
        client,
        *,
        project_dir: str | Path,
        harness_dir: str | Path,
        model: str | None = None,
        on_log: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.project_dir = Path(project_dir).resolve()
        self.harness_dir = Path(harness_dir).resolve()
        self.model = model or resolve_model_id("default")
        self.on_log = on_log
        self._slot = threading.Lock()

        with_options = getattr(client, "with_options", None)
        if callable(with_options):
            try:
                # Disable SDK-level retries so AgentRunner can keep every
                # attempt inside one shared 120-second deadline.
                client = with_options(timeout=ASK_TIMEOUT_SECONDS, max_retries=0)
            except Exception:
                # AgentRunner still supplies a decreasing timeout per request.
                pass
        self.runner = AgentRunner(client)

    @property
    def is_busy(self) -> bool:
        return self._slot.locked()

    def ask(self, question: str, callback: Callable[[str], None]) -> bool:
        """Start an asynchronous query and deliver exactly one response to callback.

        Returns True only when the query was accepted for execution. Validation and
        busy responses are delivered synchronously through the same callback.
        """
        normalized = str(question or "").strip()
        if not normalized:
            self._record("rejected", None)
            self._deliver(callback, "Usage: /ask <question>")
            return False
        if len(normalized) > QUESTION_MAX_CHARS:
            self._record("rejected", None)
            self._deliver(
                callback,
                f"Question too long ({len(normalized)} characters; maximum {QUESTION_MAX_CHARS}).",
            )
            return False
        if not self._slot.acquire(blocking=False):
            self._record("busy", None)
            self._deliver(callback, "Another code question is already being answered. Try again shortly.")
            return False

        worker = threading.Thread(
            target=self._run,
            args=(normalized, callback),
            daemon=True,
            name="telegram-code-question",
        )
        try:
            worker.start()
        except Exception:
            self._slot.release()
            self._record("error", None)
            self._deliver(callback, "Unable to start the code question service.")
            return False
        return True

    submit = ask

    def _run(self, question: str, callback: Callable[[str], None]) -> None:
        result: PhaseResult | None = None
        outcome = "error"
        response = "Unable to answer the code question."
        self._log("telegram_ask started")
        try:
            result = self.runner.run_phase(
                system_prompt=self._system_prompt(),
                user_prompt=self._user_prompt(question),
                tools=[TOOL_REGISTRY[name].schema for name in ASK_TOOL_NAMES],
                phase_name="telegram_ask",
                project_dir=self.project_dir,
                harness_dir=self.harness_dir,
                timeout=ASK_TIMEOUT_SECONDS,
                max_turns=ASK_MAX_TURNS,
                max_tokens=ASK_MAX_TOKENS,
                max_tool_result=ASK_MAX_TOOL_RESULT,
                model=self.model,
            )
            outcome = "success"
            response = self._trim_answer(result.text)
        except PhaseTimeout as exc:
            outcome = "timeout"
            result = self._result_from_metrics(exc.metrics)
            response = "The code question timed out. Please narrow the question and try again."
        except MaxTurnsExceeded as exc:
            outcome = "max_turns"
            result = self._result_from_metrics(exc.metrics)
            response = "The code question needed too many exploration steps. Please narrow it and try again."
        except MaxRetriesExceeded as exc:
            outcome = "service_unavailable"
            result = self._result_from_metrics(exc.metrics)
            response = "The language model is temporarily unavailable. Please try again later."
        except Exception as exc:
            outcome = "error"
            self._log(f"telegram_ask failed: {type(exc).__name__}")
            response = "Unable to answer the code question due to an internal error."
        finally:
            try:
                self._record(outcome, result)
                self._deliver(callback, response)
            finally:
                self._slot.release()
                self._log(f"telegram_ask finished: {outcome}")

    def _system_prompt(self) -> str:
        return (
            "You answer questions about the active software project. Inspect the "
            "current code before drawing conclusions. You may use only Read, Glob, "
            "Grep, and CodeGraph. They are read-only. Never request or imply file "
            "changes, shell commands, graph rebuilds, or tools outside that list. "
            "If CodeGraph is unavailable, continue with Read, Glob, and Grep. "
            "Answer in plain text, concisely, and distinguish verified facts from "
            "inferences. Keep the final answer under 3500 characters."
        )

    def _user_prompt(self, question: str) -> str:
        return (
            f"Project root: {self.project_dir}\n"
            f"Mission workspace: {self.harness_dir}\n"
            f"Mission state: {self._state_summary()}\n\n"
            f"Question: {question}"
        )

    def _state_summary(self) -> str:
        path = self.harness_dir / "_state.json"
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
            return "unavailable"
        if not isinstance(state, dict):
            return "unavailable"
        fields = (
            ("phase", state.get("phase")),
            ("task", state.get("task_id")),
            ("title", state.get("task_title")),
            ("position", f"{state.get('task_num', '?')}/{state.get('task_count', '?')}"),
        )
        return "; ".join(f"{name}={_short(value)}" for name, value in fields)

    @staticmethod
    def _trim_answer(text: str) -> str:
        answer = str(text or "").strip() or "No response was generated."
        if len(answer) <= ANSWER_MAX_CHARS:
            return answer
        return answer[: ANSWER_MAX_CHARS - 1].rstrip() + "…"

    def _record(self, outcome: str, result: PhaseResult | None) -> None:
        write_phase_event(
            self.harness_dir,
            "telegram_ask",
            result=outcome,
            turns=result.turns if result else 0,
            elapsed=result.elapsed if result else 0.0,
            input_tokens=result.input_tokens if result else 0,
            output_tokens=result.output_tokens if result else 0,
            model=result.model if result else self.model,
        )

    def _deliver(self, callback: Callable[[str], None], message: str) -> None:
        try:
            callback(message)
        except Exception as exc:
            self._log(f"telegram_ask callback failed: {type(exc).__name__}")

    def _log(self, message: str) -> None:
        if self.on_log:
            try:
                self.on_log(message)
            except Exception:
                pass

    def _result_from_metrics(self, metrics: dict | None) -> PhaseResult | None:
        if not metrics:
            return None
        return PhaseResult(
            text="",
            turns=int(metrics.get("turns", 0)),
            elapsed=float(metrics.get("elapsed", 0.0)),
            input_tokens=int(metrics.get("input_tokens", 0)),
            output_tokens=int(metrics.get("output_tokens", 0)),
            model=str(metrics.get("model") or self.model),
        )
