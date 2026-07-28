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
from src.core.state import MissionState
from src.mission import reporting as _reporting
from src.core.paths import SRC_DIR
from src.harness import harness_utils as _harness_utils
from src.harness import phase_logger as _phase_logger
from src.integrations import notifier as _notifier
from src.integrations import telegram_listener as _telegram_listener
from src.integrations.code_questions import CodeQuestionService
from src.integrations.telegram_lock import TelegramLock

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
        self.notify_prefix = ""
        self.telegram_handle: _telegram_listener.ListenerHandle | None = None
        self.telegram_lock: TelegramLock | None = None
        self.cleanup_done = False

    def cleanup(self):
        if self.cleanup_done:
            return
        self.cleanup_done = True
        handle = self.telegram_handle
        lock = self.telegram_lock
        self.telegram_handle = None
        self.telegram_lock = None
        _notification.set_notify_backend(_disabled_notify)
        stopped = handle is None
        try:
            if handle is not None:
                stopped = handle.stop()
                if not stopped:
                    print(
                        "WARNING: Telegram listener did not stop; bot lock retained until process exit",
                        file=sys.stderr,
                    )
        except Exception as e:
            stopped = False
            print(f"Telegram listener cleanup failed: {e}", file=sys.stderr)
        if lock is not None and stopped:
            try:
                lock.release()
            except Exception as e:
                print(f"Telegram lock cleanup failed: {e}", file=sys.stderr)
        elif lock is not None:
            # Releasing ownership while the listener still polls would permit
            # two missions to control the same bot.  Retaining both references
            # keeps the OS lock alive; the OS releases it when this process
            # exits, including after SIGINT/SIGTERM.
            self.telegram_handle = handle
            self.telegram_lock = lock

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


def _telegram_config() -> tuple[str, str] | None:
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if bool(token) != bool(chat_id):
        print(
            "ERROR: TELEGRAM_TOKEN and TELEGRAM_CHAT_ID must be configured together",
            file=sys.stderr,
        )
        raise SystemExit(2)
    if not token:
        return None
    try:
        numeric_chat_id = int(chat_id)
    except ValueError:
        numeric_chat_id = 0
    if numeric_chat_id <= 0:
        print("ERROR: TELEGRAM_CHAT_ID must identify a private chat", file=sys.stderr)
        raise SystemExit(2)
    return token, str(numeric_chat_id)


def _disabled_notify(_message: str, prefix: str = "") -> None:
    del prefix


def main():
    args = parse_args()
    resolve_args(args)
    print(
        f"task={args.task!r} branch={args.branch!r} mode={args.mode}"
        f" no_grill={args.no_grill} gate={args.gate}"
    )

    _load_env()
    telegram_config = _telegram_config()

    # Reset process-global notification hooks before attempting ownership. A
    # second mission that cannot acquire the bot lock must not emit messages.
    _notification.set_notify_backend(_disabled_notify)
    _reporting.set_notify_result_backend(_notifier.notify_result)

    harness_info = _harness_utils.setup_harness(args.branch, args.gate, resume=args.resume, task=args.task)
    harness = harness_info['harness']
    harness_win = harness_info['harness_win']

    proc = MissionProcess()
    proc.notify_prefix = _notifier.compute_notify_prefix(harness_info['project_name'])
    _notification.set_notify_prefix(proc.notify_prefix)

    atexit.register(proc.cleanup)
    signal.signal(signal.SIGTERM, proc.signal_handler)
    signal.signal(signal.SIGINT, proc.signal_handler)

    _git.ensure_develop()
    _git.setup_git(args.branch)
    project_dir = str(Path.cwd())

    client = _create_client()

    mission_state = MissionState()
    command_queue = queue.Queue()

    log = _phase_logger.make_logger(harness)

    if telegram_config is not None:
        token, chat_id = telegram_config
        owner = TelegramLock(token)
        lock_error = None
        try:
            acquired = owner.acquire()
        except OSError as exc:
            acquired = False
            lock_error = exc
            warning = f"Telegram disabled: could not acquire bot lock ({exc})"
            print(f"WARNING: {warning}", file=sys.stderr)
            log(f"WARNING: {warning}")
        if not acquired and lock_error is None:
            warning = "Telegram disabled: this bot token is already owned by another mission"
            print(f"WARNING: {warning}", file=sys.stderr)
            log(f"WARNING: {warning}")
        if acquired:
            proc.telegram_lock = owner
            try:
                question_service = CodeQuestionService(
                    client,
                    project_dir=Path.cwd(),
                    harness_dir=harness,
                    on_log=log,
                )
                proc.telegram_handle = _telegram_listener.start_listener(
                    token,
                    chat_id,
                    command_queue,
                    mission_state,
                    harness=harness,
                    question_service=question_service,
                    on_log=log,
                )
            except Exception as exc:
                warning = f"Telegram disabled: listener startup failed ({exc})"
                print(f"WARNING: {warning}", file=sys.stderr)
                log(f"WARNING: {warning}")
                proc.telegram_lock.release()
                proc.telegram_lock = None
            else:
                _notification.set_notify_backend(_notifier.notify)

    try:
        _human_input._start_stdin_listener(command_queue, mission_state)

        blocked = _block_state.BlockState()
        proc.blocked = blocked

        ctx = _context.MissionContext(
            task=args.task, branch=args.branch, mode=args.mode,
            harness=harness, harness_win=harness_win,
            project_dir=project_dir, gate="manual" if args.gate else "auto",
            no_grill=args.no_grill, max_tasks=args.max_tasks,
            resume=args.resume, notify_prefix=proc.notify_prefix,
            project_name=harness_info['project_name'],
        )

        runner = _mission_runner.create_runner(
            client, ctx, command_queue, mission_state, log, blocked,
        )
        runner.execute()
    finally:
        proc.cleanup()

    return proc


if __name__ == "__main__":
    main()
