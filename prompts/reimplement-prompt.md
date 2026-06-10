TASK_ID: {{TASK_ID}}
TASK_TITLE: {{TASK_TITLE}}
TASK_COMPLEXITY: {{TASK_COMPLEXITY}}
TASK_PIPELINE: {{TASK_PIPELINE}}
TASK_COMPLEXITY_REASON: {{TASK_COMPLEXITY_REASON}}

## Prompt Signature

- phase: reimplement.
- inputs: task id/title, `project-memory.md`, `retrieved-cases.md`, `retrieved-skills.md`, `spec.md`, reviewer `audit.md`, previous `status.md`, user feedback, `context-hot.md`.
- outputs: corrected task-scoped code/tests, updated `status.md`.
- responsibilities: diagnose the rejected feedback, fix only flagged issues, and verify locally.
- editable_artifacts (requires_grad): flagged task-scoped production files, flagged task-scoped tests, `status.md`.

This is a RE-IMPLEMENTATION. The reviewer rejected the previous implementation.

## Spec re-grounding

Before diagnosis or editing, re-read the specification and anchor the retry against it:

- Objective: use the `## Objective` / `## Objetivo` section from the specification.
- Acceptance criteria: use the `## Acceptance Criteria` / `## Criterios de Aceptacion` section from the specification.
- Deterministic checks: use `## Deterministic Check Registry` to identify the DC ids that prove the fix.
- Constraints: use explicit constraints from the specification, reviewer audit, previous status, and user feedback.
- Non-goals: preserve explicit non-goals and avoid anything the reviewer did not flag.
- Current failed checks: use the reviewer audit plus any additional user feedback below.

Your `## Diagnosis` must cite both the failed feedback and the relevant spec/acceptance criterion when applicable.

## Reviewer audit (pre-loaded)
{{AUDIT}}

{{USER_FEEDBACK}}

## Reference

### Project memory (persistent per target project)
{{PROJECT_MEMORY}}

### Similar approved mission cases
{{MISSION_CASES}}

### Retrieved verified skills
{{RETRIEVED_SKILLS}}

### Specification
{{SPEC}}

### Status (previous implementation)
{{STATUS}}

### Task routing
- complexity: {{TASK_COMPLEXITY}}
- pipeline: {{TASK_PIPELINE}}
- complexity_reason: {{TASK_COMPLEXITY_REASON}}

### Hot context (current task findings)
{{CONTEXT_HOT}}

## Required diagnosis gate

Before making any code edit, write or update status.md with a `## Diagnosis` section. Do not modify code until that section exists.

The diagnosis must explain the failed feedback in concrete terms:

```markdown
## Diagnosis
- failed_check: reviewer finding, failing test, or user retry feedback being addressed
- evidence: exact audit line, test output, file:line, or observed behavior
- root_cause: why the previous implementation was wrong
- fix_plan: smallest safe change that addresses the root cause
- non_goals: changes you will avoid because they were not requested
```

The reimplement gate will fail if the final status.md does not contain `## Diagnosis` (or `[diagnosis]`).

## Evidence anchoring

- Treat every status update as a claim that needs evidence.
- Verify fixes with a command result, relevant test, `file:line`, acceptance criterion, audit line, or observed behavior.
- If a fix cannot be verified, write `NOT_VERIFIED: reason` instead of marking it complete.
- Do not treat satisfying this prompt format as evidence that the bug is fixed.

## Required self-verification gate

Before reporting done, write a `## Self-Verification` section in status.md with:
- tests_run with command and PASS/FAIL/NOT_RUN reason
- deterministic_checks_run with DC ids from `## Deterministic Check Registry`, PASS/FAIL/NOT_RUN, and evidence
- acceptance_criteria_checked with criterion id plus test, `file:line`, audit evidence, or observed behavior
- edge_cases_considered with evidence or `NOT_APPLICABLE: reason`
- files_touched_reviewed with concrete paths
- harness_artifacts_not_written_to_target
- known_risks

The reimplement gate will fail if the final status.md does not contain `## Self-Verification` (or `[self_verification]`).

Fix ONLY what the reviewer flagged. Do not refactor, reorganize, or improve code beyond the requested changes. Update status.md with the fixes applied.
Preserve or recreate the `## Routing` section in status.md with `task_complexity:`, `task_pipeline:`, and `complexity_reason:`.
If a retrieved skill applies to the rejected issue, use it as the retry procedure and cite the verification evidence in status.md.

If a mission-validate script exists in the project root (mission-validate.cmd, .bat, .ps1, or .sh), execute it before reporting done. List all modified/created files in status.md under a ## Files section, one per line.
