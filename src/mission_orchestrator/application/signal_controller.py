from __future__ import annotations

from mission_orchestrator.application.services import AppServices
from mission_orchestrator.domain.block import BlockKind, BlockReason
from mission_orchestrator.domain.command import Command, CommandKind


class SignalController:
    def __init__(self, services: AppServices) -> None:
        self.services = services
        self.block: BlockReason | None = None

    def check_signals(self) -> bool:
        deferred: list[Command] = []
        while True:
            command = self.services.commands.get_nowait()
            if command is None:
                break
            if command.kind == CommandKind.ABORT:
                self.block = BlockReason(BlockKind.USER_ABORT, detail=command.reason or "aborted")
                self.services.notifier.notify("Mission aborted by human command.")
                self.services.commands.defer(deferred)
                return False
            if command.kind == CommandKind.PAUSE:
                if not self._wait_resume_or_abort():
                    self.services.commands.defer(deferred)
                    return False
                continue
            if command.kind == CommandKind.GATE and command.gate_mode is not None:
                self.services.state.set_gate_mode(command.gate_mode)
                continue
            deferred.append(command)
        self.services.commands.defer(deferred)
        return True

    def _wait_resume_or_abort(self) -> bool:
        self.services.notifier.notify("Mission paused. Send /resume or /abort.")
        deferred: list[Command] = []
        while True:
            command = self.services.commands.get(timeout_seconds=5.0)
            if command is None:
                continue
            if command.kind == CommandKind.RESUME:
                self.services.notifier.notify("Mission resumed.")
                self.services.commands.defer(deferred)
                return True
            if command.kind == CommandKind.ABORT:
                self.block = BlockReason(BlockKind.USER_ABORT, detail=command.reason or "aborted")
                self.services.notifier.notify("Mission aborted while paused.")
                self.services.commands.defer(deferred)
                return False
            if command.kind == CommandKind.GATE and command.gate_mode is not None:
                self.services.state.set_gate_mode(command.gate_mode)
            else:
                deferred.append(command)

