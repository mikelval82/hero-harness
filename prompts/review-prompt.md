TASK_ID: {{TASK_ID}}
TASK_TITLE: {{TASK_TITLE}}
TASK_COMPLEXITY: {{TASK_COMPLEXITY}}
TASK_PIPELINE: {{TASK_PIPELINE}}
TASK_COMPLEXITY_REASON: {{TASK_COMPLEXITY_REASON}}

## Prompt Signature

- phase: review.
- inputs: task id/title, `project-memory.md`, `retrieved-cases.md`, `retrieved-skills.md`, `spec.md`, `plan.md`, `decisions.md`, `status.md`, modified files, tests, deterministic check registry, code graph instructions.
- outputs: `audit.md`.
- responsibilities: produce evidence-anchored technical review, deterministic check results, semantic audit, gradients, taxonomy, and verdict.
- editable_artifacts (requires_grad): `audit.md`.

## Artifacts to review against

### Project memory (persistent per target project)
{{PROJECT_MEMORY}}

### Similar approved mission cases
{{MISSION_CASES}}

### Retrieved verified skills
{{RETRIEVED_SKILLS}}

### Specification (EARS requirements)
{{SPEC}}

### Plan
{{PLAN}}

### Decisions (ADR)
{{DECISIONS}}

### Task routing
- complexity: {{TASK_COMPLEXITY}}
- pipeline: {{TASK_PIPELINE}}
- complexity_reason: {{TASK_COMPLEXITY_REASON}}

{{GRAPH_INSTRUCTIONS}}

Verify each EARS requirement (Rn) and acceptance criterion (CAn) from the spec against the implemented code. Cite file:line for each.
Extract `## Deterministic Check Registry (check_registry)` from the spec and execute or inspect every `DC*` check. Preserve each check's `requirement:` link and compare each result against the check's `expected:` field. If `type: command`, run the exact command unless it is destructive, requires network, or cannot run in this environment; otherwise mark it NOT_RUN with a concrete reason and provide equivalent evidence if available. If `type: static_inspection` or `manual`, cite file:line, validation output, or observed behavior. Do not approve when a check tied to an acceptance criterion fails or remains NOT_RUN without strong alternative evidence.
Use the code graph to verify that all callers of modified functions were updated and no dead code was introduced.
Treat `status.md`, self-verification, and checkboxes as claims, not evidence. A claim is supported only by file:line, test/command output, validation output, a spec requirement, or observed behavior. Unsupported material claims must be listed under `unsupported_claims` and must block approval when they affect correctness.
If a retrieved skill applied to the task, audit whether the implementation followed the relevant procedure. Do not reject solely for ignoring a non-applicable skill.

Your audit.md must separate:
- `## Technical Review (technical_review)`: correctness against spec, plan, decisions, tests, validation, and code graph evidence.
- `### Evidence Anchoring (evidence_anchoring)`: status claims checked, unsupported claims, evidence quality, instruction-compliance risk, and concrete evidence.
- `### Evaluation Hacking Check (evaluation_hacking_check)`: hardcoding of expected outputs, special-casing visible tests/fixtures/seeds, superficial acceptance criteria satisfaction, hidden shortcuts, evidence, and risk.
- `### Deterministic Check Registry (check_registry)`: source registry, executed checks, failed checks, not-run checks, and per-check evidence.
- `### Gradient Findings (textual_gradients)`: every non-approved finding localized to a variable/artifact with `variable`, `role`, `objective`, `feedback`, `required_change`, `constraints`, and `evidence`. If there are no findings, write `- none`.
- `## Failure Taxonomy (failure_taxonomy)`: `failure_type`, `recoverability_lost_at_stage`, `severity`, `evidence`, `linked_gradients`, and `next_action`. Use `failure_type: none` and `recoverability_lost_at_stage: none` for APPROVED.
- `## Semantic Audit (semantic_audit)`: alignment with the user's real intent, value delivered, scope control, and risk of satisfying visible criteria without solving the actual problem.

The `### Evidence Anchoring` section must include these exact fields: `status_claims_checked:`, `unsupported_claims:`, `evidence_quality:`, `instruction_compliance_risk:`, and `evidence:`.
The `### Deterministic Check Registry` section must include these exact fields: `registry_source:`, `checks_executed:`, `failed_checks:`, and `not_run_checks:`.

Do NOT write to context-hot.md. Your verdict lives exclusively in audit.md.

If a mission-validate script exists in the project root (mission-validate.cmd, .bat, .ps1, or .sh), execute it. DO NOT clean the workspace after review.
