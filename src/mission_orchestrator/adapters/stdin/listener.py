from __future__ import annotations

import sys
import threading

from mission_orchestrator.domain.command import parse_control_command
from mission_orchestrator.ports.command_bus import CommandBus


class StdinListener:
    def __init__(self, command_bus: CommandBus) -> None:
        self.command_bus = command_bus

    def start_if_tty(self) -> threading.Thread | None:
        if not sys.stdin.isatty():
            return None
        thread = threading.Thread(target=self._run, name="stdin-listener", daemon=True)
        thread.start()
        return thread

    def _run(self) -> None:
        while True:
            try:
                line = sys.stdin.readline()
            except Exception:
                return
            if not line:
                return
            command = parse_control_command(line)
            if command:
                self.command_bus.publish(command)

