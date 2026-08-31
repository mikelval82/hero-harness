from __future__ import annotations

import threading
import urllib.error
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from mission_orchestrator.adapters.filesystem.mission_registry import MissionRegistry
from mission_orchestrator.adapters.telegram.api import get_updates, send_message
from mission_orchestrator.adapters.telegram.commands import ARTIFACTS, parse_telegram_command
from mission_orchestrator.adapters.telegram.lock import TelegramLock, TelegramOffsetStore
from mission_orchestrator.ports.artifacts import ArtifactStore
from mission_orchestrator.ports.command_bus import CommandBus
from mission_orchestrator.ports.state_store import MissionStateStore


class ListenerStatus(str, Enum):
    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"
    FATAL = "fatal"
    STOPPED = "stopped"


@dataclass(frozen=True)
class ListenerHealth:
    status: ListenerStatus
    detail: str = ""


class ListenerHandle:
    def __init__(self, thread: threading.Thread, stop_event: threading.Event, listener: "TelegramListener") -> None:
        self._thread = thread
        self._stop_event = stop_event
        self._listener = listener

    def stop(self, timeout: float = 10.0) -> bool:
        self._stop_event.set()
        if self._thread is not threading.current_thread():
            self._thread.join(timeout=max(0.0, timeout))
        return not self._thread.is_alive()

    @property
    def health(self) -> ListenerHealth:
        return self._listener.health


class TelegramListener:
    """One token, one controlled mission, at-most-once control command delivery."""

    def __init__(
        self,
        *,
        token: str,
        chat_id: str,
        mission_tag: str,
        artifacts: ArtifactStore,
        state: MissionStateStore,
        commands: CommandBus,
        registry: MissionRegistry,
        storage_root: Path | None = None,
    ) -> None:
        self.token = token
        self.chat_id = str(chat_id)
        self.mission_tag = mission_tag
        self.artifacts = artifacts
        self.state = state
        self.commands = commands
        self.registry = registry
        self.lock = TelegramLock(token, storage_root)
        self.offset_store = TelegramOffsetStore(token, storage_root)
        self._stop_event = threading.Event()
        self._health = ListenerHealth(ListenerStatus.STARTING)
        self._health_lock = threading.Lock()

    @property
    def health(self) -> ListenerHealth:
        with self._health_lock:
            return self._health

    def start(self) -> ListenerHandle:
        if not self.lock.acquire():
            raise RuntimeError("Telegram bot is already controlled by another mission")
        try:
            offset = self.offset_store.synchronize_backlog(
                lambda requested: get_updates(self.token, requested, timeout=0)
            )
        except Exception:
            self.lock.release()
            raise
        thread = threading.Thread(target=self._run, args=(offset,), name="telegram-listener", daemon=True)
        thread.start()
        return ListenerHandle(thread, self._stop_event, self)

    def _run(self, offset: int) -> None:
        backoff = 0.25
        try:
            while not self._stop_event.is_set():
                try:
                    updates = get_updates(self.token, offset, timeout=5)
                    self._set_health(ListenerStatus.RUNNING)
                    backoff = 0.25
                except urllib.error.HTTPError as exc:
                    if exc.code in {401, 403, 409}:
                        self._set_health(ListenerStatus.FATAL, f"Telegram HTTP {exc.code}")
                        self._stop_event.set()
                        break
                    self._set_health(ListenerStatus.DEGRADED, f"Telegram HTTP {exc.code}")
                    self._stop_event.wait(backoff)
                    backoff = min(backoff * 2, 5.0)
                    continue
                except (urllib.error.URLError, TimeoutError, OSError) as exc:
                    self._set_health(ListenerStatus.DEGRADED, type(exc).__name__)
                    self._stop_event.wait(backoff)
                    backoff = min(backoff * 2, 5.0)
                    continue
                except Exception as exc:
                    self._set_health(ListenerStatus.DEGRADED, type(exc).__name__)
                    self._stop_event.wait(backoff)
                    backoff = min(backoff * 2, 5.0)
                    continue
                for update in updates:
                    if self._stop_event.is_set():
                        break
                    update_id = update.get("update_id")
                    if not isinstance(update_id, int) or isinstance(update_id, bool) or update_id < offset:
                        continue
                    offset = update_id + 1
                    # Persist before dispatch: crash may lose a command but cannot replay it into another mission.
                    self.offset_store.write(offset)
                    self._handle_update(update)
        finally:
            self.lock.release()
            if self.health.status is not ListenerStatus.FATAL:
                self._set_health(ListenerStatus.STOPPED)

    def _handle_update(self, update: dict) -> None:
        message = update.get("message") or update.get("edited_message") or {}
        chat = message.get("chat") or {}
        sender = message.get("from") or {}
        if chat.get("type") not in {None, "private"}:
            return
        if str(chat.get("id")) != self.chat_id or str(sender.get("id")) != self.chat_id:
            return
        self._handle(str(message.get("text", "")))

    def _handle(self, text: str) -> None:
        parsed = parse_telegram_command(text)
        if parsed is None:
            return
        if parsed.target and parsed.target != self.mission_tag:
            return
        if parsed.name in ARTIFACTS:
            self._send_artifact(ARTIFACTS[parsed.name])
            return
        if parsed.name == "status":
            snapshot = self.state.load_snapshot()
            self._send(str(snapshot.to_json() if snapshot else "No state yet."))
            return
        if parsed.name == "log":
            lines = self.artifacts.read_text("mission.log", default="").splitlines()[-30:]
            self._send("\n".join(lines) or "No log yet.")
            return
        if parsed.name == "missions":
            missions = self.registry.active()
            self._send("\n".join(sorted(missions)) or "No active missions.")
            return
        if parsed.name == "help":
            self._send("Read: /status /log /missions /brief /plan /decisions /spec /audit. Control: /abort @mission-tag")
            return
        if parsed.bus_command:
            if parsed.target != self.mission_tag:
                self._send("Control commands require the exact active target: /command @mission-tag")
                return
            self.commands.publish(parsed.bus_command)

    def _send_artifact(self, artifact: str) -> None:
        self._send(self.artifacts.read_text(artifact, default=f"{artifact} is not available yet.")[:8000])

    def _send(self, text: str) -> None:
        send_message(self.token, self.chat_id, text)

    def _set_health(self, status: ListenerStatus, detail: str = "") -> None:
        with self._health_lock:
            self._health = ListenerHealth(status, detail)
