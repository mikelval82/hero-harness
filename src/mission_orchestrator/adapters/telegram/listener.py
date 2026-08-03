from __future__ import annotations

import threading
from pathlib import Path

from mission_orchestrator.adapters.filesystem.mission_registry import MissionRegistry
from mission_orchestrator.adapters.telegram.api import get_updates, send_message
from mission_orchestrator.adapters.telegram.commands import ARTIFACTS, parse_telegram_command
from mission_orchestrator.ports.artifacts import ArtifactStore
from mission_orchestrator.ports.command_bus import CommandBus
from mission_orchestrator.ports.state_store import MissionStateStore


class TelegramListener:
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
    ) -> None:
        self.token = token
        self.chat_id = str(chat_id)
        self.mission_tag = mission_tag
        self.artifacts = artifacts
        self.state = state
        self.commands = commands
        self.registry = registry
        self.offset: int | None = None

    def start(self) -> threading.Thread:
        thread = threading.Thread(target=self._run, name="telegram-listener", daemon=True)
        thread.start()
        return thread

    def _run(self) -> None:
        while True:
            try:
                updates = get_updates(self.token, self.offset, timeout=60)
            except Exception:
                continue
            for update in updates:
                self.offset = int(update.get("update_id", 0)) + 1
                message = update.get("message") or update.get("edited_message") or {}
                chat = message.get("chat") or {}
                if str(chat.get("id")) != self.chat_id:
                    continue
                text = str(message.get("text", ""))
                self._handle(text)

    def _handle(self, text: str) -> None:
        parsed = parse_telegram_command(text)
        if parsed is None:
            return
        if parsed.target and parsed.target not in self.mission_tag:
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
            self._send("\n".join(f"{tag}: {info.get('harness_path')}" for tag, info in missions.items()))
            return
        if parsed.name == "help":
            self._send(
                "/status /log /missions /brief /plan /decisions /spec /audit /statusfile "
                "/brainstorm /tasks /hot /warm /abort /pause /resume /approve /reject /retry /skip /gate"
            )
            return
        if parsed.bus_command:
            self.commands.publish(parsed.bus_command)

    def _send_artifact(self, artifact: str) -> None:
        content = self.artifacts.read_text(artifact, default=f"{artifact} is not available yet.")
        self._send(content[:8000])

    def _send(self, text: str) -> None:
        send_message(self.token, self.chat_id, text)

