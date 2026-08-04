from __future__ import annotations

import argparse
import atexit
import os
import signal
from pathlib import Path

from mission_orchestrator.adapters.analysis.service import SQLiteCodeGraphService
from mission_orchestrator.adapters.anthropic.client import AnthropicAgentClient
from mission_orchestrator.adapters.command_bus import QueueCommandBus
from mission_orchestrator.adapters.events.decorators import PublishingLogger, PublishingNotifier
from mission_orchestrator.adapters.events.sqlite_log import SqliteEventLog
from mission_orchestrator.adapters.filesystem.artifact_store import FilesystemArtifactStore
from mission_orchestrator.adapters.filesystem.logger import FilesystemMissionLogger
from mission_orchestrator.adapters.filesystem.mission_registry import MissionRegistry
from mission_orchestrator.adapters.filesystem.prompt_renderer import FilesystemPromptRenderer
from mission_orchestrator.adapters.filesystem.state_store import FilesystemMissionStateStore
from mission_orchestrator.adapters.filesystem.task_repository import JsonTaskRepository
from mission_orchestrator.adapters.filesystem.workspace import WorkspaceManager, sanitize
from mission_orchestrator.adapters.git.service import SubprocessGitService
from mission_orchestrator.adapters.stdin.listener import StdinListener
from mission_orchestrator.adapters.telegram.listener import TelegramListener
from mission_orchestrator.adapters.telegram.notifier import TelegramNotifier
from mission_orchestrator.adapters.tools.registry import default_tool_registry
from mission_orchestrator.adapters.web.server import MissionWebServer
from mission_orchestrator.application.gate_evaluator import MarkdownGateEvaluator
from mission_orchestrator.application.orchestrator import MissionOrchestrator
from mission_orchestrator.application.services import AppServices
from mission_orchestrator.domain.command import Command, CommandKind
from mission_orchestrator.domain.mission import GateMode, MissionContext, MissionMode
from mission_orchestrator.ports.tool_registry import ToolEnvironment


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    load_dotenv(Path.cwd() / ".env")
    mode = MissionMode.PLAN if args.plan_only else MissionMode(args.mode)
    task = resolve_task(args)
    branch = args.branch_opt or args.branch or sanitize(task.lower().replace(" ", "-"), max_len=60)
    gate_mode = GateMode.from_bool(args.gate)
    project_dir = Path.cwd().resolve()

    workspace = WorkspaceManager().setup(
        project_dir=project_dir,
        branch=branch,
        resume=args.resume,
        gate_mode=gate_mode,
    )
    artifacts = FilesystemArtifactStore(workspace.harness_dir)
    events = SqliteEventLog(workspace.harness_dir, mission=workspace.mission_tag)
    logger = PublishingLogger(FilesystemMissionLogger(artifacts), events)
    tasks = JsonTaskRepository(artifacts)
    state = FilesystemMissionStateStore(artifacts, gate_mode)
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
    git.setup_branch(branch)

    tool_registry = default_tool_registry(logger)
    tool_env = ToolEnvironment(project_dir, workspace.harness_dir)
    agent = AnthropicAgentClient(tool_registry, tool_env, commands)
    repo_root = Path(__file__).resolve().parents[2]
    prompts = FilesystemPromptRenderer(
        repo_root / "prompts",
        repo_root / "agents",
        str(workspace.harness_dir),
    )
    services = AppServices(
        artifacts=artifacts,
        tasks=tasks,
        state=state,
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
        task=task,
        branch=branch,
        mode=mode,
        project_dir=project_dir,
        harness_dir=workspace.harness_dir,
        harness_display_path=str(workspace.harness_dir),
        gate_mode=gate_mode,
        no_grill=args.no_grill,
        max_tasks=args.max_tasks,
        resume=args.resume,
        mission_tag=workspace.mission_tag,
        project_name=workspace.project_name,
        project_scope_dir=workspace.project_scope_dir,
    )
    _install_signal_handlers(commands)
    atexit.register(lambda: logger.log("process exit"))
    if os.environ.get("TELEGRAM_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"):
        TelegramListener(
            token=os.environ["TELEGRAM_TOKEN"],
            chat_id=os.environ["TELEGRAM_CHAT_ID"],
            mission_tag=workspace.mission_tag,
            artifacts=artifacts,
            state=state,
            commands=commands,
            registry=registry,
        ).start()
    StdinListener(commands).start_if_tty()
    if args.web:
        web = MissionWebServer(
            workspace.harness_dir, workspace.mission_tag, port=args.web_port, commands=commands
        )
        logger.log(f"web server: {web.start()}")
    result = MissionOrchestrator(services, context).run()
    return 0 if result.block is None else 2


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="mission")
    parser.add_argument("task", nargs="?")
    parser.add_argument("branch", nargs="?")
    parser.add_argument("--no-grill", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--gate", action="store_true")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--mode", choices=[mode.value for mode in MissionMode], default="full")
    parser.add_argument("--task-file")
    parser.add_argument("--branch", dest="branch_opt")
    parser.add_argument("--max-tasks", type=int, default=20)
    parser.add_argument("--web", action="store_true")
    parser.add_argument("--web-port", type=int, default=8765)
    return parser.parse_args(argv)


def resolve_task(args: argparse.Namespace) -> str:
    if args.task_file:
        return Path(args.task_file).read_text(encoding="utf-8").strip()
    if args.task:
        return args.task
    return input("Mission task: ").strip()


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _install_signal_handlers(commands: QueueCommandBus) -> None:
    def handler(signum, frame) -> None:  # noqa: ANN001
        commands.publish(Command(CommandKind.ABORT, reason=f"signal {signum}"))

    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(signum, handler)
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())

