from __future__ import annotations

import re
from typing import Optional, Callable

from src.core.context import PhaseName


MIN_GATE_LINES = 4

GATE_REQUIRED_MARKERS: dict[PhaseName, list[list[str]]] = {
    PhaseName.GRILL: [
        ["## Objective", "## Objetivo"],
        ["## Key Decisions", "## Decisiones"],
    ],
    PhaseName.SPEC: [
        ["## Objetivo", "## Objective"],
        ["## Comportamiento Esperado", "## Expected Behavior", "## Behaviour"],
        ["## Deterministic Check Registry", "## Registro de Checks Deterministas", "check_registry"],
        ["id: DC"],
        ["requirement:"],
        ["type:"],
        ["expected:"],
    ],
    PhaseName.PLAN: [
        ["## Changes", "## Pasos", "## Archivos", "## Steps", "## Implementacion", "## Implementación"],
    ],
    PhaseName.IMPLEMENT: [
        ["## Routing", "## Task Routing", "[routing]"],
        ["complexity_reason:"],
        ["## Self-Verification", "## Self Verification", "[self_verification]"],
    ],
    PhaseName.REVIEW: [
        ["## Verdict", "## Veredicto"],
        ["## Technical Review", "technical_review", "## Revision Tecnica"],
        ["### Evidence Anchoring", "## Evidence Anchoring", "evidence_anchoring"],
        ["status_claims_checked:"],
        ["unsupported_claims:"],
        ["evidence_quality:"],
        ["instruction_compliance_risk:"],
        ["### Evaluation Hacking Check", "## Evaluation Hacking Check", "evaluation_hacking_check"],
        ["hardcoding_outputs:"],
        ["special_casing_tests:"],
        ["superficial_acceptance:"],
        ["### Deterministic Check Registry", "## Deterministic Check Registry", "check_registry"],
        ["registry_source:"],
        ["checks_executed:"],
        ["failed_checks:"],
        ["not_run_checks:"],
        ["### Gradient Findings", "## Gradient Findings", "textual_gradients"],
        ["## Failure Taxonomy", "failure_taxonomy", "## Taxonomia de Fallos"],
        ["failure_type:"],
        ["recoverability_lost_at_stage:"],
        ["## Semantic Audit", "semantic_audit", "## Auditoria Semantica"],
    ],
    PhaseName.REIMPLEMENT: [
        ["## Diagnosis", "## Diagnostico", "[diagnosis]"],
        ["## Self-Verification", "## Self Verification", "[self_verification]"],
    ],
}


def _gate_fail(phase_name: str, reason: str, log: Optional[Callable] = None) -> tuple[bool, str]:
    msg = f"GATE FAIL: {phase_name} — {reason}"
    print(msg)
    if log:
        log(msg)
    return False, reason


def check_gate(gate_file, phase_name: str, log: Optional[Callable] = None) -> tuple[bool, str]:
    if not gate_file.is_file():
        return _gate_fail(phase_name, f"file {gate_file.name} not found", log)
    content = gate_file.read_text(encoding="utf-8")
    lines = content.splitlines()

    if len(lines) < MIN_GATE_LINES:
        return _gate_fail(phase_name, f"artifact too short ({len(lines)} lines, min {MIN_GATE_LINES})", log)

    tail = lines[-5:] if len(lines) >= 5 else lines
    if any("**STATUS: BLOCKED**" in line for line in tail):
        return _gate_fail(phase_name, "agent reported BLOCKED", log)
    if not any("**STATUS: DONE**" in line or "**STATUS: ALREADY_DONE**" in line for line in tail):
        return _gate_fail(phase_name, "no STATUS: DONE found", log)

    phase_type = phase_name.split("[")[0] if "[" in phase_name else phase_name
    marker_groups = GATE_REQUIRED_MARKERS.get(phase_type, [])
    for variants in marker_groups:
        if not any(v in content for v in variants):
            return _gate_fail(phase_name, f"missing required section (expected one of: {variants})", log)

    print(f"GATE PASS: {phase_name}")
    if log:
        log(f"GATE PASS: {phase_name}")
    return True, ""


def parse_plan_steps(plan_text: str) -> list[str]:
    headings = GATE_REQUIRED_MARKERS[PhaseName.PLAN][0]
    pattern = "|".join(re.escape(h) for h in headings)
    m = re.search(rf'^({pattern})\s*$', plan_text, re.MULTILINE)
    if not m:
        return []
    section_start = m.end()
    end_match = re.search(r'^## ', plan_text[section_start:], re.MULTILINE)
    section = plan_text[section_start:section_start + end_match.start()] if end_match else plan_text[section_start:]
    chunks = re.split(r'(?=^### \d+\.)', section, flags=re.MULTILINE)
    return [c.strip() for c in chunks if re.match(r'^### \d+\.', c)]
