from __future__ import annotations

from dataclasses import dataclass, field

from mission_orchestrator.ports.agent_client import AgentClient
from mission_orchestrator.ports.artifacts import ArtifactStore
from mission_orchestrator.ports.code_graph import CodeGraphService
from mission_orchestrator.ports.command_bus import CommandBus
from mission_orchestrator.ports.events import EventPublisher, NullEventPublisher
from mission_orchestrator.ports.gate_evaluator import GateEvaluator
from mission_orchestrator.ports.git_service import GitService
from mission_orchestrator.ports.logger import MissionLogger
from mission_orchestrator.ports.notifier import Notifier
from mission_orchestrator.ports.prompt_renderer import PromptRenderer
from mission_orchestrator.ports.state_store import MissionStateStore
from mission_orchestrator.ports.task_repository import TaskRepository
from mission_orchestrator.ports.tool_registry import ToolRegistry


@dataclass
class AppServices:
    artifacts: ArtifactStore
    tasks: TaskRepository
    state: MissionStateStore
    commands: CommandBus
    agent: AgentClient
    tools: ToolRegistry
    prompts: PromptRenderer
    gates: GateEvaluator
    notifier: Notifier
    git: GitService
    code_graph: CodeGraphService
    logger: MissionLogger
    events: EventPublisher = field(default_factory=NullEventPublisher)

