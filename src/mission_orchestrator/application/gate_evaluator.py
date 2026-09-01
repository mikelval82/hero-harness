from __future__ import annotations

import json
import re

from mission_orchestrator.domain.phase import GateResult
from mission_orchestrator.domain.validation import ValidationKind, ValidationStatus
from mission_orchestrator.application.validation_obligations import read_validation_obligations
from mission_orchestrator.ports.artifacts import ArtifactStore


OBJECTIVE_RE = re.compile(r"^##\s+(Objective|Objetivo)\b", re.IGNORECASE | re.MULTILINE)
DECISIONS_RE = re.compile(r"^##\s+(Key Decisions|Decisiones)\b", re.IGNORECASE | re.MULTILINE)
EXPECTED_RE = re.compile(
    r"^##\s+(Expected Behavior|Behaviour|Comportamiento esperado|Behavior)\b",
    re.IGNORECASE | re.MULTILINE,
)
PLAN_RE = re.compile(
    r"^##\s+(Changes|Steps|Files|Implementation|Cambios|Pasos|Archivos|Implementacion|Implementación|Plan)\b",
    re.IGNORECASE | re.MULTILINE,
)
VERDICT_RE = re.compile(r"^##\s+(Verdict|Veredicto)\b", re.IGNORECASE | re.MULTILINE)


class MarkdownGateEvaluator:
    def __init__(self, artifacts: ArtifactStore) -> None:
        self.artifacts = artifacts

    def evaluate(self, phase_name: str, artifact_name: str) -> GateResult:
        if not self.artifacts.exists(artifact_name):
            return GateResult(False, f"{artifact_name} does not exist")
        text = self.artifacts.read_text(artifact_name, default="")
        lines = text.splitlines()
        if len(lines) < 4:
            return GateResult(False, f"{artifact_name} has fewer than 4 lines")
        tail = "\n".join(lines[-5:])
        if "**STATUS: BLOCKED**" in tail:
            return GateResult(False, f"{artifact_name} is BLOCKED")
        if "**STATUS: DONE**" not in tail and "**STATUS: ALREADY_DONE**" not in tail:
            return GateResult(False, f"{artifact_name} does not end with DONE/ALREADY_DONE")
        marker = self._marker_check(phase_name, text)
        if marker:
            return GateResult(False, marker)
        if phase_name == "review":
            validation = self._validation_check()
            if validation:
                return GateResult(False, validation)
        return GateResult(True, "")

    def _validation_check(self) -> str:
        try:
            obligations = read_validation_obligations(
                self.artifacts.read_text("task-contract.json", default="")
            )
        except ValueError as exc:
            return str(exc)
        for obligation in obligations:
            if obligation.kind is not ValidationKind.TRUSTED_COMMAND:
                continue
            evidence_name = f"validation-evidence/{obligation.check_id}.json"
            if not self.artifacts.exists(evidence_name):
                return f"validation {obligation.id} is NOT_RUN: missing {evidence_name}"
            try:
                evidence = json.loads(self.artifacts.read_text(evidence_name))
                status = ValidationStatus(str(evidence.get("status")))
            except (json.JSONDecodeError, ValueError) as exc:
                return f"validation {obligation.id} has invalid evidence: {exc}"
            if evidence.get("check_id") != obligation.check_id:
                return f"validation {obligation.id} evidence check_id does not match"
            if status is ValidationStatus.FAIL:
                return f"validation {obligation.id} FAILED"
            if status is ValidationStatus.NOT_RUN:
                return f"validation {obligation.id} is NOT_RUN without explicit alternative evidence"
            if status is not ValidationStatus.PASS:
                return f"validation {obligation.id} has unsupported status"
        return ""

    def _marker_check(self, phase_name: str, text: str) -> str:
        if phase_name == "grill":
            return self._require(text, (OBJECTIVE_RE, DECISIONS_RE), "objective and decisions sections")
        if phase_name == "spec":
            return self._require(text, (OBJECTIVE_RE, EXPECTED_RE), "objective and expected behavior sections")
        if phase_name == "plan":
            return self._require(text, (PLAN_RE,), "changes/steps/files/implementation section")
        if phase_name == "review":
            return self._require(text, (VERDICT_RE,), "verdict section")
        return ""

    @staticmethod
    def _require(text: str, patterns: tuple[re.Pattern[str], ...], label: str) -> str:
        if all(pattern.search(text) for pattern in patterns):
            return ""
        return f"missing {label}"
