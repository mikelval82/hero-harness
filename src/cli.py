import argparse
import atexit
import os
import queue
import signal
import sys
from pathlib import Path

from src.core import block_state as _block_state
from src.core.block_state import BlockKind, BlockReason
from src.core import context as _context
from src.core import git as _git
from src.mission import human_input as _human_input
from src.mission import runner as _mission_runner
from src.core import notification as _notification
from src.mission import reporting as _reporting
from src.core.paths import SRC_DIR
from src.harness import harness_utils as _harness_utils
from src.harness import phase_logger as _phase_logger
from src.harness import registry as _registry
from src.integrations import notifier as _notifier
from src.integrations import telegram_listener as _telegram_listener

MAX_TASKS = 20


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Mission orchestrator")
    parser.add_argument("task", nargs="?", default=None)
    parser.add_argument("branch_pos", nargs="?", default=None)
    parser.add_argument("--no-grill", action="store_true", dest="no_grill")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--gate", action="store_true")
    parser.add_argument("--spec-only", action="store_true", dest="spec_only")
    parser.add_argument("--spec-plan", action="store_true", dest="spec_plan")
    parser.add_argument(
        "--mode",
        choices=["full", "focused", "spec", "spec-plan", "explore", "hotfix"],
        default=None,
    )
    parser.add_argument("--task-file", dest="task_file", default=None)
    parser.add_argument("--branch", dest="branch_flag", default=None)
    parser.add_argument("--max-tasks", type=int, default=MAX_TASKS, dest="max_tasks")

    args = parser.parse_args(argv)

    alias_modes = []
    if args.spec_only:
        alias_modes.append("spec")
    if args.spec_plan:
        alias_modes.append("spec-plan")

    if args.mode is not None:
        pass
    elif len(alias_modes) > 1:
        parser.error("--spec-only and --spec-plan are mutually exclusive")
    elif alias_modes:
        args.mode = alias_modes[0]
    else:
        args.mode = "full"

    args.branch = args.branch_flag or args.branch_pos
    del args.spec_only
    del args.spec_plan
    del args.branch_pos
    del args.branch_flag

    return args


def resolve_args(args):
    if args.task_file:
        path = Path(args.task_file)
        if not path.is_file():
            print(f"ERROR: task file not found: {args.task_file}", file=sys.stderr)
            sys.exit(1)
        args.task = path.read_text(encoding="utf-8").strip()

    if not args.task:
        args.task = input("Task description: ").strip()

    if not args.task:
        print("ERROR: no task provided", file=sys.stderr)
        sys.exit(1)

    if not args.branch:
        slug = _harness_utils.sanitize_name(args.task[:40], max_len=40)
        args.branch = f"feature/{slug}"

    return args


class MissionProcess:

    def __init__(self):
        self.blocked: _block_state.BlockState | None = None
        self.mission_tag = ""
        self.notify_prefix = ""
        self.cleanup_done = False

    def cleanup(self):
        if self.cleanup_done or not self.mission_tag:
            return
        self.cleanup_done = True
        try:
            _registry.unregister_mission(self.mission_tag)
            remaining = _registry.list_missions()
            if len(remaining) == 0:
                print("Listener stopped (last mission exiting)")
        except Exception as e:
            print(f"cleanup failed: {e}", file=sys.stderr)

    def signal_handler(self, signum, frame):
        sig_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
        if self.blocked is not None:
            self.blocked.reason = BlockReason(BlockKind.SIGNAL, detail=sig_name)
        self.cleanup()
        sys.exit(1)


def _load_env():
    # Load from .env.local in CLAUDE_HOME first (personal credentials)
    env_local = Path(os.environ.get("CLAUDE_HOME", SRC_DIR.parent)) / ".env.local"
    if env_local.is_file():
        for line in env_local.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())

    # Then load from .env in src/ (shared configuration)
    env_file = SRC_DIR / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


def _create_client():
    import anthropic
    return anthropic.Anthropic()


def main():
    args = parse_args()
    resolve_args(args)
    print(
        f"task={args.task!r} branch={args.branch!r} mode={args.mode}"
        f" no_grill={args.no_grill} gate={args.gate}"
    )

    _load_env()

    _notification.set_notify_backend(_notifier.notify)
    _reporting.set_notify_result_backend(_notifier.notify_result)

    harness_info = _harness_utils.setup_harness(args.branch, args.gate, resume=args.resume, task=args.task)
    harness = harness_info['harness']
    harness_win = harness_info['harness_win']

    proc = MissionProcess()
    proc.notify_prefix = _notifier.compute_notify_prefix(harness_info['project_name'])
    proc.mission_tag = harness_info['mission_tag']

    atexit.register(proc.cleanup)
    signal.signal(signal.SIGTERM, proc.signal_handler)
    signal.signal(signal.SIGINT, proc.signal_handler)

    _git.ensure_develop()
    _git.setup_git(args.branch)
    project_dir = str(Path.cwd())

    _registry.register_mission(proc.mission_tag, harness_win, os.getpid())

    client = _create_client()

    mission_state = _telegram_listener.MissionState()
    command_queue = queue.Queue()

    token = os.environ.get("TELEGRAM_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if token and chat_id:
        _telegram_listener.start_listener(token, chat_id, command_queue, mission_state, harness=harness)

    _human_input._start_stdin_listener(command_queue)

    log = _phase_logger.make_logger(harness)

    blocked = _block_state.BlockState()
    proc.blocked = blocked

    ctx = _context.MissionContext(
        task=args.task, branch=args.branch, mode=args.mode,
        harness=harness, harness_win=harness_win,
        project_dir=project_dir, gate="manual" if args.gate else "auto",
        no_grill=args.no_grill, max_tasks=args.max_tasks,
        resume=args.resume, notify_prefix=proc.notify_prefix,
        mission_tag=proc.mission_tag,
        project_name=harness_info['project_name'],
    )

    runner = _mission_runner.create_runner(client, ctx, command_queue, mission_state, log, blocked)
    runner.execute()

    return proc


if __name__ == "__main__":
    main()
