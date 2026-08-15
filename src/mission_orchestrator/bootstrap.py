from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from mission_orchestrator.adapters.analysis.service import SQLiteCodeGraphService
from mission_orchestrator.adapters.anthropic.client import AnthropicAgentClient
from mission_orchestrator.adapters.command_bus import QueueCommandBus
from mission_orchestrator.adapters.conversation.sqlite_log import SqliteConversationLog
from mission_orchestrator.adapters.events.decorators import PublishingLogger, PublishingNotifier
from mission_orchestrator.adapters.events.sqlite_log import SqliteEventLog
from mission_orchestrator.adapters.filesystem.artifact_store import FilesystemArtifactStore
from mission_orchestrator.adapters.filesystem.logger import FilesystemMissionLogger
from mission_orchestrator.adapters.filesystem.mission_registry import MissionRegistry
from mission_orchestrator.adapters.filesystem.prompt_renderer import FilesystemPromptRenderer
from mission_orchestrator.adapters.filesystem.state_store import FilesystemMissionStateStore
from mission_orchestrator.adapters.filesystem.task_repository import JsonTaskRepository
from mission_orchestrator.adapters.filesystem.workspace import WorkspaceInfo, WorkspaceManager
from mission_orchestrator.adapters.git.service import SubprocessGitService
from mission_orchestrator.adapters.telegram.notifier import TelegramNotifier
from mission_orchestrator.adapters.tools.registry import default_tool_registry
from mission_orchestrator.application.gate_evaluator import MarkdownGateEvaluator
from mission_orchestrator.application.services import AppServices
from mission_orchestrator.domain.mission import GateMode, MissionContext, MissionMode
from mission_orchestrator.ports.tool_registry import ToolEnvironment


@dataclass(frozen=True)
class RuntimeConfig:
    task: str
    branch: str
    mode: MissionMode
    project_dir: Path
    gate_mode: GateMode
    no_grill: bool = False
    max_tasks: int = 20
    resume: bool = False


@dataclass(frozen=True)
class MissionRuntime:
    services: AppServices
    context: MissionContext
    workspace: WorkspaceInfo
    registry: MissionRegistry
    commands: QueueCommandBus


def build_runtime(config: RuntimeConfig) -> MissionRuntime:
    project_dir = config.project_dir.resolve()
    workspace = WorkspaceManager().setup(
        project_dir=project_dir,
        branch=config.branch,
        resume=config.resume,
        gate_mode=config.gate_mode,
    )
    artifacts = FilesystemArtifactStore(workspace.harness_dir)
    events = SqliteEventLog(workspace.harness_dir, mission=workspace.mission_tag)
    logger = PublishingLogger(FilesystemMissionLogger(artifacts), events)
    commands = QueueCommandBus()
    registry = MissionRegistry()
    registry.register(workspace.mission_tag, workspace.harness_dir)
    notifier = PublishingNotifier(
        TelegramNotifier(
            os.environ.get("TELEGRAM_TOKEN"),
            os.environ.get("TELEGRAM_CHAT_ID"),
            prefix=f"[{workspace.project_name}]",
        ),
        events,
    )
    git = SubprocessGitService(project_dir)
    git.ensure_develop()
    git.setup_branch(config.branch)
    tool_registry = default_tool_registry(logger)
    conversation = SqliteConversationLog(workspace.harness_dir / "conversation.db")
    agent = AnthropicAgentClient(
        tool_registry,
        ToolEnvironment(project_dir, workspace.harness_dir),
        commands,
        conversation=conversation,
        events=events,
    )
    repo_root = Path(__file__).resolve().parents[2]
    prompts = FilesystemPromptRenderer(
        repo_root / "prompts",
        repo_root / "agents",
        str(workspace.harness_dir),
    )
    services = AppServices(
        artifacts=artifacts,
        tasks=JsonTaskRepository(artifacts),
        state=FilesystemMissionStateStore(artifacts, config.gate_mode),
        commands=commands,
        agent=agent,
        tools=tool_registry,
        prompts=prompts,
        gates=MarkdownGateEvaluator(artifacts),
        notifier=notifier,
        git=git,
        code_graph=SQLiteCodeGraphService(workspace.harness_dir),
        logger=logger,
        events=events,
    )
    context = MissionContext(
        task=config.task,
        branch=config.branch,
        mode=config.mode,
        project_dir=project_dir,
        harness_dir=workspace.harness_dir,
        harness_display_path=str(workspace.harness_dir),
        gate_mode=config.gate_mode,
        no_grill=config.no_grill,
        max_tasks=config.max_tasks,
        resume=config.resume,
        mission_tag=workspace.mission_tag,
        project_name=workspace.project_name,
        project_scope_dir=workspace.project_scope_dir,
    )
    return MissionRuntime(services, context, workspace, registry, commands)