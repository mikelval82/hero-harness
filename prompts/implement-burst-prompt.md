TASK_ID: {{TASK_ID}}
TASK_TITLE: {{TASK_TITLE}}
TASK_COMPLEXITY: {{TASK_COMPLEXITY}}
TASK_PIPELINE: {{TASK_PIPELINE}}
TASK_COMPLEXITY_REASON: {{TASK_COMPLEXITY_REASON}}

## Prompt Signature

- phase: implement_bursts.
- inputs: task id/title, current plan step, `project-memory.md`, `retrieved-cases.md`, `retrieved-skills.md`, `spec.md`, `decisions.md`, progress, `context-cold.md`, `context-hot.md`, code graph instructions.
- outputs: task-scoped code/tests, `_burst_progress.md`, final `status.md` when instructed.
- responsibilities: implement only the current burst step and preserve spec alignment.
- editable_artifacts (requires_grad): task-scoped production files, task-scoped tests, `_burst_progress.md`, final `status.md`.

## Spec re-grounding

Before editing in this burst, re-read the specification below and anchor the current step against it:

- Objective: use the `## Objective` / `## Objetivo` section from the specification.
- Acceptance criteria: use the `## Acceptance Criteria` / `## Criterios de Aceptacion` section from the specification.
- Deterministic checks: use `## Deterministic Check Registry` as the verification checklist for final status.
- Constraints: use explicit constraints from the specification and decisions.
- Non-goals: infer only from explicit non-goals, excluded scope, or decisions; do not invent new scope.
- Current failed checks or risks: there is no reviewer audit yet in burst mode, so treat unresolved issues in `Progress from prior bursts` as current failures/risks.

If the current step conflicts with the spec, decisions, or progress, stop and document the conflict in status.md instead of drifting.

## Prior context (pre-loaded)

### Project memory (persistent per target project)
{{PROJECT_MEMORY}}

### Similar approved mission cases
{{MISSION_CASES}}

### Retrieved verified skills
{{RETRIEVED_SKILLS}}

### Cold context (accumulated cross-task summary)
{{CONTEXT_COLD}}

### Hot context (current task findings)
{{CONTEXT_HOT}}

### Specification
{{SPEC}}

### Decisions
{{DECISIONS}}

### Task routing
- complexity: {{TASK_COMPLEXITY}}
- pipeline: {{TASK_PIPELINE}}
- complexity_reason: {{TASK_COMPLEXITY_REASON}}

### Code graph
{{GRAPH_INSTRUCTIONS}}

### Current step
{{PLAN_STEP}}

### Progress from prior bursts
{{PROGRESS}}

Implement ONLY the current step above. Do not work on other steps.
If a retrieved skill applies to this burst, follow the relevant part of its procedure and include evidence in `_burst_progress.md` or final `status.md`.

After completing the step, append a summary of what was done (files created/modified, key decisions) to `$CLAUDE_HARNESS/_burst_progress.md`.
Treat the burst summary as evidence, not ceremony: include command results, tests, `file:line`, or observed behavior for the step. If the step cannot be verified, write `NOT_VERIFIED: reason`.

{{FINAL_INSTRUCTIONS}}
