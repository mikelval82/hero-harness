"""Single-mission Telegram listener.

The caller owns the bot lock and supplies the exact mission state, queue and
workspace. No command can resolve or select any other mission.
"""

from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable

from src.core.state import MissionState
from src.integrations import telegram_api
from src.integrations.code_questions import CodeQuestionService
from src.integrations.telegram_api import TelegramAPIError
from src.integrations.telegram_commands import (
    ARTIFACT_COMMANDS,
    HELP_TEXT,
    MUTATING_COMMANDS,
    READ_COMMANDS,
    cmd_ask,
    cmd_read_artifact,
)
from src.integrations.telegram_lock import TelegramOffsetStore
from src.mission.control import CommandRouter


POLL_TIMEOUT_SECONDS = 5
MAX_POLL_BACKOFF_SECONDS = 5.0
STOP_TIMEOUT_SECONDS = 35.0
STARTUP_MAX_ATTEMPTS = 3


class ListenerStatus(str, Enum):
    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"
    FATAL = "fatal"
    STOPPED = "stopped"


@dataclass(frozen=True)
class HealthSnapshot:
    status: ListenerStatus
    last_error: str


class ListenerHealth:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._status = ListenerStatus.STARTING
        self._last_error = ""

    def set(self, status: ListenerStatus, error: str = "") -> None:
        with self._lock:
            self._status = status
            self._last_error = error

    def snapshot(self) -> HealthSnapshot:
        with self._lock:
            return HealthSnapshot(self._status, self._last_error)


class ListenerHandle:
    """Lifecycle handle for the listener thread."""

    def __init__(
        self,
        thread: threading.Thread,
        stop_event: threading.Event,
        health: ListenerHealth,
    ) -> None:
        self._thread = thread
        self._stop_event = stop_event
        self.health = health
        self._stop_lock = threading.Lock()

    @property
    def is_alive(self) -> bool:
        return self._thread.is_alive()

    def stop(self, timeout: float = STOP_TIMEOUT_SECONDS) -> bool:
        """Request shutdown and wait briefly; safe to invoke repeatedly."""

        with self._stop_lock:
            self._stop_event.set()
            if self._thread is not threading.current_thread():
                self._thread.join(timeout=max(0.0, timeout))
            stopped = not self._thread.is_alive()
            snapshot = self.health.snapshot()
            if stopped and snapshot.status is not ListenerStatus.FATAL:
                self.health.set(ListenerStatus.STOPPED, snapshot.last_error)
            return stopped


def _parse_command(text: str) -> tuple[str, list[str]] | None:
    words = text.strip().split()
    if not words or not words[0].startswith("/"):
        return None
    # Telegram appends @BotUsername in groups and may preserve it in forwarded
    # command text. It identifies the bot, never a mission.
    command = words[0].lower().split("@", 1)[0]
    return command, words[1:]


def handle_command(
    token: str,
    chat_id: str,
    text: str,
    harness: Path,
    *,
    router: CommandRouter,
    mission_state: MissionState,
    question_service: CodeQuestionService,
    update_id: int | str | None = None,
    delivery_allowed: Callable[[], bool] | None = None,
) -> None:
    parsed = _parse_command(text)
    if parsed is None:
        return
    command, args = parsed

    if command in {"/help", "/start"}:
        if args:
            telegram_api.send_message(token, chat_id, f"Usage: {command}")
        else:
            telegram_api.send_message(token, chat_id, HELP_TEXT)
        return
    if command == "/ask":
        cmd_ask(
            token,
            chat_id,
            args,
            question_service,
            mission_state=mission_state,
            delivery_allowed=delivery_allowed,
        )
        return
    if command in ARTIFACT_COMMANDS:
        cmd_read_artifact(
            token,
            chat_id,
            args,
            ARTIFACT_COMMANDS[command],
            harness,
        )
        return
    read_handler = READ_COMMANDS.get(command)
    if read_handler is not None:
        read_handler(
            token,
            chat_id,
            args,
            harness,
            mission_state=mission_state,
        )
        return
    if command in MUTATING_COMMANDS:
        outcome = router.route(
            command,
            args,
            update_id=update_id,
            source="telegram",
        )
        telegram_api.send_message(token, chat_id, outcome.message)
        return
    telegram_api.send_message(token, chat_id, f"Unknown command: {command}\n\n{HELP_TEXT}")


def notify_pending_interaction(
    token: str,
    chat_id: str,
    mission_state: MissionState,
) -> bool:
    """Deliver the active prompt once, marking it only after full delivery."""

    interaction = mission_state.get_interaction()
    if interaction is None or interaction.notified:
        return False
    prompt = interaction.prompt.strip() or f"Input required for {interaction.kind.value}."
    result = telegram_api.send_message(token, chat_id, prompt)
    if not result.ok:
        return False
    return mission_state.mark_interaction_notified(interaction.id)


def _authorized_text(update: dict, configured_chat_id: str) -> str | None:
    message = update.get("message")
    if not isinstance(message, dict):
        return None
    chat = message.get("chat")
    sender = message.get("from")
    if not isinstance(chat, dict) or not isinstance(sender, dict):
        return None
    if chat.get("type") != "private":
        return None
    if str(chat.get("id")) != configured_chat_id:
        return None
    if str(sender.get("id")) != configured_chat_id:
        return None
    text = message.get("text")
    return text.strip() if isinstance(text, str) and text.strip() else None


def _report(
    message: str,
    *,
    health: ListenerHealth,
    status: ListenerStatus,
    on_log: Callable[[str], None] | None,
) -> None:
    health.set(status, message)
    line = f"Telegram listener {status.value}: {message}"
    if on_log is not None:
        try:
            on_log(line)
        except Exception:
            pass
    print(line, file=sys.stderr)


def poll_loop(
    token: str,
    chat_id: str,
    harness: Path,
    *,
    router: CommandRouter,
    mission_state: MissionState,
    question_service: CodeQuestionService,
    offset_store: TelegramOffsetStore,
    stop_event: threading.Event,
    health: ListenerHealth,
    on_log: Callable[[str], None] | None = None,
    initial_offset: int | None = None,
) -> None:
    backoff = 0.5
    offset_write_backoff = 0.5
    offset = initial_offset

    while not stop_event.is_set():
        try:
            if offset is None:
                offset = offset_store.load_or_synchronize(
                    lambda requested: telegram_api.get_updates(
                        token,
                        requested,
                        timeout=0,
                        limit=1,
                    )
                )
            try:
                notify_pending_interaction(token, chat_id, mission_state)
            except TelegramAPIError as exc:
                # A transient send failure must not prevent polling control
                # commands such as /abort. Permanent auth/conflict failures do
                # stop this listener because polling cannot recover either.
                status = ListenerStatus.FATAL if exc.fatal else ListenerStatus.DEGRADED
                _report(str(exc), health=health, status=status, on_log=on_log)
                if exc.fatal:
                    stop_event.set()
                    break
            except Exception as exc:
                _report(
                    f"pending interaction notification failed: {type(exc).__name__}: {exc}",
                    health=health,
                    status=ListenerStatus.DEGRADED,
                    on_log=on_log,
                )
            updates = telegram_api.get_updates(
                token,
                offset,
                timeout=POLL_TIMEOUT_SECONDS,
            )
            health.set(ListenerStatus.RUNNING)
            backoff = 0.5
        except TelegramAPIError as exc:
            status = ListenerStatus.FATAL if exc.fatal else ListenerStatus.DEGRADED
            _report(str(exc), health=health, status=status, on_log=on_log)
            if exc.fatal:
                stop_event.set()
                break
            delay = exc.retry_after if exc.retry_after is not None else backoff
            stop_event.wait(min(max(0.0, delay), MAX_POLL_BACKOFF_SECONDS))
            backoff = min(backoff * 2, MAX_POLL_BACKOFF_SECONDS)
            continue
        except Exception as exc:
            _report(
                f"{type(exc).__name__}: {exc}",
                health=health,
                status=ListenerStatus.DEGRADED,
                on_log=on_log,
            )
            stop_event.wait(backoff)
            backoff = min(backoff * 2, MAX_POLL_BACKOFF_SECONDS)
            continue

        # Telegram returns update_id values in ascending order. Preserve that
        # order so a malformed item cannot make a mixed-type sort fail.
        for update in updates:
            if stop_event.is_set():
                break
            update_id = update.get("update_id")
            if not isinstance(update_id, int) or isinstance(update_id, bool):
                _report(
                    "ignored update without a valid update_id",
                    health=health,
                    status=ListenerStatus.DEGRADED,
                    on_log=on_log,
                )
                continue
            if update_id < offset:
                continue

            # Persist before dispatch. A crash may lose this command, but it can
            # never replay against a later mission.
            next_offset = update_id + 1
            try:
                offset_store.write(next_offset)
            except Exception as exc:
                _report(
                    f"could not persist update offset: {type(exc).__name__}: {exc}",
                    health=health,
                    status=ListenerStatus.DEGRADED,
                    on_log=on_log,
                )
                stop_event.wait(offset_write_backoff)
                offset_write_backoff = min(
                    offset_write_backoff * 2,
                    MAX_POLL_BACKOFF_SECONDS,
                )
                break
            offset = next_offset
            offset_write_backoff = 0.5

            text = _authorized_text(update, chat_id)
            if text is None:
                continue
            try:
                handle_command(
                    token,
                    chat_id,
                    text,
                    harness,
                    router=router,
                    mission_state=mission_state,
                    question_service=question_service,
                    update_id=update_id,
                    delivery_allowed=lambda: not stop_event.is_set(),
                )
            except TelegramAPIError as exc:
                status = ListenerStatus.FATAL if exc.fatal else ListenerStatus.DEGRADED
                _report(str(exc), health=health, status=status, on_log=on_log)
                if exc.fatal:
                    stop_event.set()
                    break
            except Exception as exc:
                # One malformed command/handler must not terminate polling or
                # prevent later updates from being acknowledged.
                _report(
                    f"command {update_id} failed: {type(exc).__name__}: {exc}",
                    health=health,
                    status=ListenerStatus.DEGRADED,
                    on_log=on_log,
                )

    if health.snapshot().status is not ListenerStatus.FATAL:
        health.set(ListenerStatus.STOPPED, health.snapshot().last_error)


def _synchronize_startup_offset(
    token: str,
    offset_store: TelegramOffsetStore,
) -> int:
    """Discard backlog before exposing the listener to the mission.

    Keeping this handshake synchronous closes the window where the mission
    announces itself and a valid immediate reply is then mistaken for old
    backlog. Transient Telegram failures get a small bounded retry budget;
    permanent failures propagate and disable Telegram for this mission.
    """

    backoff = 0.5
    for attempt in range(STARTUP_MAX_ATTEMPTS):
        try:
            return offset_store.load_or_synchronize(
                lambda requested: telegram_api.get_updates(
                    token,
                    requested,
                    timeout=0,
                    limit=1,
                )
            )
        except TelegramAPIError as exc:
            if exc.fatal or not exc.retryable or attempt + 1 >= STARTUP_MAX_ATTEMPTS:
                raise
            delay = exc.retry_after if exc.retry_after is not None else backoff
            time.sleep(min(max(0.0, delay), MAX_POLL_BACKOFF_SECONDS))
            backoff = min(backoff * 2, MAX_POLL_BACKOFF_SECONDS)

    raise RuntimeError("unreachable Telegram startup retry state")


def start_listener(
    token: str,
    chat_id: str | int,
    command_queue,
    mission_state: MissionState,
    *,
    harness: Path,
    question_service: CodeQuestionService,
    on_log: Callable[[str], None] | None = None,
    offset_store: TelegramOffsetStore | None = None,
) -> ListenerHandle:
    """Start a daemon listener already bound to one mission."""

    if not token:
        raise ValueError("Telegram token is required")
    configured_chat_id = str(chat_id).strip()
    if not configured_chat_id:
        raise ValueError("Telegram chat id is required")

    router = CommandRouter(mission_state, command_queue)
    stop_event = threading.Event()
    health = ListenerHealth()
    store = offset_store or TelegramOffsetStore(token)
    initial_offset = _synchronize_startup_offset(token, store)
    thread = threading.Thread(
        target=poll_loop,
        kwargs={
            "token": token,
            "chat_id": configured_chat_id,
            "harness": Path(harness),
            "router": router,
            "mission_state": mission_state,
            "question_service": question_service,
            "offset_store": store,
            "stop_event": stop_event,
            "health": health,
            "on_log": on_log,
            "initial_offset": initial_offset,
        },
        daemon=True,
        name="telegram-listener",
    )
    handle = ListenerHandle(thread, stop_event, health)
    thread.start()
    return handle
