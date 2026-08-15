from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from mission_orchestrator.adapters.events.decorators import PublishingLogger
from mission_orchestrator.application.errors import MaxRetriesExceeded, MaxTurnsExceeded
from mission_orchestrator.application.phase_executor import PhaseExecutor
from mission_orchestrator.domain.mission import MissionMode
from mission_orchestrator.domain.phase import PhaseName, PhaseResult
from mission_orchestrator.ports.events import NullEventPublisher

from tests.application.test_orchestrator import FakeAgent, make_services


class RecordingEvents:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []

    def publish(self, kind: str, payload: dict) -> None:
        self.published.append((kind, payload))

    def events_since(self, after_id: int, limit: int = 200) -> list:
        return []


class FailingAgent:
    def run_phase(self, request):  # noqa: ANN001
        raise MaxRetriesExceeded("api exhausted", None)

    def run_conversation(self, request):  # noqa: ANN001
        raise MaxRetriesExceeded("api exhausted", None)


class SilentAgent:
    def run_phase(self, request):  # noqa: ANN001
        return PhaseResult("", 1, 0.01, 1, 1)

    def run_conversation(self, request):  # noqa: ANN001
        return PhaseResult("", 1, 0.01, 1, 1)


class MaxTurnsAgent:
    def run_phase(self, request):  # noqa: ANN001
        raise MaxTurnsExceeded("maximum turns exceeded", PhaseResult("", 30, 12.5, 900, 100))

    def run_conversation(self, request):  # noqa: ANN001
        return self.run_phase(request)


class PhaseProgressEventsTest(unittest.TestCase):
    def _executor(self, tmp: Path, agent) -> tuple[PhaseExecutor, RecordingEvents]:  # noqa: ANN001
        services, context, _ = make_services(tmp, MissionMode.FOCUSED, agent=agent)
        events = RecordingEvents()
        services.events = events
        return PhaseExecutor(services, context), events

    def test_p1_successful_phase_publishes_started_and_completed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            agent = FakeAgent(None)  # artifacts aligned below
            services, context, _ = make_services(tmp, MissionMode.FOCUSED, agent=agent)
            agent.artifacts = services.artifacts
            events = RecordingEvents()
            services.events = events

            execution = PhaseExecutor(services, context).run(PhaseName.RESEARCH)

            self.assertIsNone(execution.block)
            kinds = [kind for kind, _ in events.published]
            self.assertEqual(kinds[0], "phase_started")
            self.assertEqual(
                events.published[0][1],
                {"phase": "research", "mode": "focused", "max_turns": 75},
            )
            ended = dict(events.published)[
                "phase_ended"
            ]
            self.assertEqual(ended["outcome"], "completed")
            self.assertEqual(ended["phase"], "research")
            self.assertEqual(ended["turns"], 1)
            self.assertIn("input_tokens", ended)
            self.assertIn("elapsed_seconds", ended)

    def test_p2_agent_loop_error_publishes_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            executor, events = self._executor(Path(raw), FailingAgent())

            execution = executor.run(PhaseName.RESEARCH)

            self.assertIsNotNone(execution.block)
            ended = [payload for kind, payload in events.published if kind == "phase_ended"]
            self.assertEqual(len(ended), 1)
            self.assertEqual(ended[0]["outcome"], "blocked")
            self.assertEqual(ended[0]["block_kind"], "api_retries")
            self.assertIn("api exhausted", ended[0]["detail"])

    def test_p3_gate_failure_publishes_blocked_gate_fail(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            executor, events = self._executor(Path(raw), SilentAgent())

            execution = executor.run(PhaseName.RESEARCH, evaluate_gate=True)

            self.assertIsNotNone(execution.block)
            ended = [payload for kind, payload in events.published if kind == "phase_ended"]
            self.assertEqual(len(ended), 1)
            self.assertEqual(ended[0]["outcome"], "blocked")
            self.assertEqual(ended[0]["block_kind"], "gate_fail")

    def test_max_turns_block_preserves_usage_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            executor, events = self._executor(Path(raw), MaxTurnsAgent())

            execution = executor.run(PhaseName.REVIEW)

            self.assertIsNotNone(execution.block)
            ended = [payload for kind, payload in events.published if kind == "phase_ended"]
            self.assertEqual(ended[0]["turns"], 30)
            self.assertEqual(ended[0]["input_tokens"], 900)
            self.assertEqual(ended[0]["output_tokens"], 100)

    def test_p4_publishing_logger_emits_tool_call_events(self) -> None:
        calls: list[tuple] = []

        class Inner:
            def log(self, message: str) -> None:
                calls.append(("log", message))

            def tool_call(self, name: str, input: dict) -> None:
                calls.append(("tool_call", name))

            def metric(self, record: dict) -> None:
                calls.append(("metric", record))

        events = RecordingEvents()
        logger = PublishingLogger(Inner(), events)
        logger.tool_call("Read", {"file_path": "src/mod.py"})
        logger.tool_call("GraphQuery", {"query": "nodes"})

        self.assertEqual(
            events.published[0],
            ("tool_call", {"tool": "Read", "summary": "Reading src/mod.py"}),
        )
        self.assertEqual(
            events.published[1],
            ("tool_call", {"tool": "GraphQuery", "summary": "Tool GraphQuery"}),
        )
        self.assertEqual([c[0] for c in calls], ["tool_call", "tool_call"])

    def test_p5_null_publisher_is_inert(self) -> None:
        null = NullEventPublisher()
        null.publish("anything", {"x": 1})
        self.assertEqual(null.events_since(0), [])

    def test_p5_default_services_use_null_publisher(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            services, _, _ = make_services(Path(raw), MissionMode.FOCUSED, agent=SilentAgent())
            self.assertIsInstance(services.events, NullEventPublisher)


if __name__ == "__main__":
    unittest.main()
