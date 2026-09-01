import threading
import time
from types import SimpleNamespace

from mission_orchestrator.application.code_questions import CodeQuestionService
from mission_orchestrator.domain.phase import PhaseResult


class _Logger:
    def __init__(self):
        self.metrics = []
    def metric(self, record):
        self.metrics.append(record)


class _Tools:
    def schemas_for(self, authority):
        assert authority.tools == ("Read", "Glob", "Grep", "CodeGraph")
        assert authority.allow_project_writes is False
        assert authority.harness_mutation_tools == ()
        return [{"name": name} for name in authority.tools]


class _Agent:
    def run_phase(self, request):
        assert request.phase_name == "ask"
        assert request.tool_names == ("Read", "Glob", "Grep", "CodeGraph")
        return PhaseResult("verified answer", 1, 0.01, 3, 2)


def test_ask_is_async_bounded_read_only_and_redacts_content():
    logger = _Logger()
    services = SimpleNamespace(tools=_Tools(), agent=_Agent(), logger=logger)
    context = SimpleNamespace(project_dir="project")
    service = CodeQuestionService(services, context)
    operation = service.submit("SECRET question")
    done = threading.Event()
    for _ in range(100):
        if service.get(operation["operation_id"])["status"] != "running":
            done.set()
            break
        time.sleep(0.001)
    assert done.is_set()
    result = service.get(operation["operation_id"])
    assert result["status"] == "completed"
    assert result["answer"] == "verified answer"
    assert all("SECRET" not in str(record) for record in logger.metrics)


def test_ask_rejects_empty_and_oversized_questions():
    services = SimpleNamespace(tools=_Tools(), agent=_Agent(), logger=_Logger())
    service = CodeQuestionService(services, SimpleNamespace(project_dir="project"))
    for value in ("", "x" * 2001):
        try:
            service.submit(value)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid question accepted")
