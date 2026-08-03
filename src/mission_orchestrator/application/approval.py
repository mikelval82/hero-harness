from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from mission_orchestrator.adapters.design.store import DesignStore
from mission_orchestrator.domain.command import CommandKind
from mission_orchestrator.domain.design import ApplyStatus, Intent
from mission_orchestrator.ports.command_bus import CommandBus
from mission_orchestrator.ports.notifier import Notifier

_ACCEPTED = {CommandKind.APPROVE, CommandKind.REJECT, CommandKind.ABORT}


class ApprovalOutcome(Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    ABORTED = "aborted"


@dataclass(frozen=True)
class ApprovalDecision:
    kind: ApprovalOutcome
    snapshot_id: str = ""
    reason: str = ""


class ApprovalCoordinator:
    def __init__(
        self,
        *,
        store: DesignStore,
        commands: CommandBus,
        notifier: Notifier,
        harness_dir: Path,
        project_scope_dir: Path,
        observed_revision: int,
    ) -> None:
        self.store = store
        self.commands = commands
        self.notifier = notifier
        self.harness_dir = harness_dir
        self.project_scope_dir = project_scope_dir
        self.observed_revision = observed_revision

    def wait_for_approval(self) -> ApprovalDecision:
        revision = self.store.current_revision()
        self.notifier.notify(self._summary(revision))
        command = self._wait_typed()
        if command.kind == CommandKind.ABORT:
            return ApprovalDecision(ApprovalOutcome.ABORTED, reason=command.reason or "aborted")
        if command.kind == CommandKind.REJECT:
            return ApprovalDecision(ApprovalOutcome.REJECTED, reason=command.reason or "rejected")
        result = self.store.approve(base_revision=revision, observed_revision=self.observed_revision)
        if result.status != ApplyStatus.APPLIED or result.snapshot is None:
            self.notifier.notify("Approval failed: the map changed while waiting. Review and approve again.")
            return self.wait_for_approval()
        snapshot = result.snapshot
        self._export(snapshot)
        self.notifier.notify(f"Architecture approved: snapshot {snapshot['snapshot_id']}")
        return ApprovalDecision(ApprovalOutcome.APPROVED, snapshot_id=snapshot["snapshot_id"])

    def _wait_typed(self):
        deferred = []
        try:
            while True:
                command = self.commands.get(timeout_seconds=5.0)
                if command is None:
                    continue
                if command.kind in _ACCEPTED:
                    return command
                deferred.append(command)
        finally:
            self.commands.defer(deferred)

    def _summary(self, revision: int) -> str:
        nodes = self.store.nodes()
        by_intent = {intent.value: 0 for intent in Intent}
        for node in nodes:
            by_intent[node.intent] = by_intent.get(node.intent, 0) + 1
        counts = ", ".join(f"{intent}: {count}" for intent, count in by_intent.items() if count)
        return (
            f"Design map at revision {revision} awaits approval ({counts or 'empty map'}). "
            "Send /approve, /reject <reason> or /abort."
        )

    def _export(self, snapshot: dict) -> None:
        payload = json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n"
        (self.harness_dir / "approved_snapshot.json").write_text(payload, encoding="utf-8")
        durable = self.project_scope_dir / "snapshots"
        durable.mkdir(parents=True, exist_ok=True)
        (durable / f"{snapshot['snapshot_id']}.json").write_text(payload, encoding="utf-8")
