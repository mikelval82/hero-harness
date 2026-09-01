from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from time import monotonic

from mission_orchestrator.application.errors import MaxRetriesExceeded, MaxTurnsExceeded, PhaseTimeout
from mission_orchestrator.domain.phase import PhaseAuthority, PhaseName, PhaseResult
from mission_orchestrator.ports.agent_client import AgentRequest
from mission_orchestrator.ports.tool_registry import ToolAuthorizationError


QUESTION_MAX_CHARS = 2_000
ANSWER_MAX_CHARS = 3_500
ASK_MAX_TURNS = 8
ASK_TIMEOUT_SECONDS = 120
ASK_MAX_TOKENS = 1_200
ASK_MAX_TOOL_RESULT = 12_000
ASK_TOOLS = ("Read", "Glob", "Grep", "CodeGraph")


@dataclass
class AskOperation:
    operation_id: str
    status: str = "running"
    answer: str = ""
    error: str = ""
    turns: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    elapsed_seconds: float = 0.0

    def to_json(self) -> dict[str, object]:
        return {
            "operation_id": self.operation_id,
            "status": self.status,
            "answer": self.answer if self.status == "completed" else "",
            "error": self.error,
            "turns": self.turns,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "elapsed_seconds": self.elapsed_seconds,
        }


class CodeQuestionService:
    """Bounded, asynchronous and strictly read-only code questions."""

    def __init__(self, services, context) -> None:  # noqa: ANN001
        self.services = services
        self.context = context
        self._slot = threading.Lock()
        self._lock = threading.Lock()
        self._operations: dict[str, AskOperation] = {}

    def submit(self, question: str) -> dict[str, object]:
        normalized = str(question or "").strip()
        if not normalized:
            raise ValueError("question is required")
        if len(normalized) > QUESTION_MAX_CHARS:
            raise ValueError(f"question exceeds {QUESTION_MAX_CHARS} characters")
        operation_id = uuid.uuid4().hex
        operation = AskOperation(operation_id)
        with self._lock:
            self._operations[operation_id] = operation
        if not self._slot.acquire(blocking=False):
            operation.status = "busy"
            operation.error = "another code question is already running"
            self._record(operation)
            return operation.to_json()
        thread = threading.Thread(target=self._run, args=(operation, normalized), daemon=True, name="code-question")
        try:
            thread.start()
        except Exception:
            self._slot.release()
            operation.status = "unavailable"
            operation.error = "code question service unavailable"
            self._record(operation)
        return operation.to_json()

    def get(self, operation_id: str) -> dict[str, object]:
        with self._lock:
            operation = self._operations.get(operation_id)
        if operation is None:
            raise ValueError("ask operation not found")
        return operation.to_json()

    def _run(self, operation: AskOperation, question: str) -> None:
        started = monotonic()
        try:
            authority = PhaseAuthority(PhaseName.RESEARCH, ASK_TOOLS)
            schemas = self.services.tools.schemas_for(authority)
            request = AgentRequest(
                phase_name="ask",
                system_prompt=(
                    "Answer questions about the project using only Read, Glob, Grep, and CodeGraph. "
                    "These tools are read-only. Never propose writes or shell commands. "
                    "Distinguish verified facts from inferences and be concise."
                ),
                user_prompt=f"Project: {self.context.project_dir}\nQuestion: {question}",
                tool_names=ASK_TOOLS,
                tool_schemas=schemas,
                authority=authority,
                max_turns=ASK_MAX_TURNS,
                timeout_seconds=ASK_TIMEOUT_SECONDS,
            )
            result = self.services.agent.run_phase(request)
            operation.status = "completed"
            operation.answer = _trim(result.text)
            self._metrics(operation, result)
        except (PhaseTimeout, MaxTurnsExceeded, MaxRetriesExceeded) as error:
            operation.status = {
                PhaseTimeout: "timeout",
                MaxTurnsExceeded: "max_turns",
                MaxRetriesExceeded: "unavailable",
            }[type(error)]
            operation.error = operation.status
            metrics = getattr(error, "metrics", None)
            if metrics:
                self._metrics(operation, metrics)
        except ToolAuthorizationError:
            operation.status = "unavailable"
            operation.error = "read-only tools unavailable"
        except Exception:
            operation.status = "unavailable"
            operation.error = "code question service unavailable"
        finally:
            operation.elapsed_seconds = round(monotonic() - started, 3)
            self._record(operation)
            self._slot.release()

    @staticmethod
    def _metrics(operation: AskOperation, result: PhaseResult) -> None:
        operation.turns = result.turns
        operation.input_tokens = result.input_tokens
        operation.output_tokens = result.output_tokens
        operation.elapsed_seconds = result.elapsed_seconds

    def _record(self, operation: AskOperation) -> None:
        self.services.logger.metric({
            "event": "code_question",
            "outcome": operation.status,
            "turns": operation.turns,
            "input_tokens": operation.input_tokens,
            "output_tokens": operation.output_tokens,
            "elapsed_seconds": operation.elapsed_seconds,
        })


def _trim(text: str) -> str:
    answer = str(text or "").strip() or "No response was generated."
    return answer if len(answer) <= ANSWER_MAX_CHARS else answer[: ANSWER_MAX_CHARS - 1].rstrip() + "…"
