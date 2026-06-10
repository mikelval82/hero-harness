TASK_ID: {{TASK_ID}}
TASK_TITLE: {{TASK_TITLE}}
TASK_COMPLEXITY: {{TASK_COMPLEXITY}}
TASK_PIPELINE: {{TASK_PIPELINE}}
TASK_COMPLEXITY_REASON: {{TASK_COMPLEXITY_REASON}}

## Prompt Signature

- phase: plan.
- inputs: task id/title, `project-memory.md`, `retrieved-cases.md`, `retrieved-skills.md`, `spec.md`, `brainstorm.md`, `tasks.json`, `brief.md`, `context-cold.md`, `context-hot.md`, code graph instructions.
- outputs: `plan.md`, `decisions.md`, appended `context-hot.md`.
- responsibilities: choose a scoped implementation path and verification strategy.
- editable_artifacts (requires_grad): `plan.md`, `decisions.md`, `context-hot.md`.

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

### Research findings
{{BRAINSTORM}}

### Task list
{{TASKS}}

### Task routing
- complexity: {{TASK_COMPLEXITY}}
- pipeline: {{TASK_PIPELINE}}
- complexity_reason: {{TASK_COMPLEXITY_REASON}}

### Mission brief (alignment from grill)
{{BRIEF}}

### Specification
{{SPEC}}

{{GRAPH_INSTRUCTIONS}}

Only explore files not already covered above. Append risks and discarded approaches to context-hot.md under ## Planner ({{TASK_ID}}).
Do NOT create status.md. Only produce: plan.md and decisions.md.
Use retrieved skills as reusable procedures for plan shape and verification when applicable; do not force them onto unrelated work.

Evidence anchoring:
- Each plan step must be motivated by a spec criterion, ADR, code path, or observed risk.
- Do not include steps just to show diligence. Remove steps that cannot be anchored to concrete evidence.
- In `## Verification`, distinguish executable checks from manual checks and state what evidence each check should produce.

## Instruction budget

plan.md MUST be at most 80 lines. Focus on interfaces and contracts between components, not implementation details or lines of code. Each step should describe WHAT to change and WHY, not HOW line-by-line. If you need more than 80 lines, you are being too granular — consolidate.
