TASK_ID: {{TASK_ID}}
TASK_TITLE: {{TASK_TITLE}}
TASK_COMPLEXITY: {{TASK_COMPLEXITY}}
TASK_PIPELINE: {{TASK_PIPELINE}}
TASK_COMPLEXITY_REASON: {{TASK_COMPLEXITY_REASON}}

## Prompt Signature

- phase: spec.
- inputs: task id/title, `project-memory.md`, `retrieved-cases.md`, `retrieved-skills.md`, `brainstorm.md`, `tasks.json`, `brief.md`, `context-cold.md`, `context-hot.md`, code graph instructions.
- outputs: `spec.md`, appended `context-hot.md`.
- responsibilities: define objective, EARS requirements, edge cases, acceptance criteria, and deterministic checks.
- editable_artifacts (requires_grad): `spec.md`, `context-hot.md`.

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

### Code graph
{{GRAPH_INSTRUCTIONS}}

Only explore files not already covered above. Append discoveries to context-hot.md under ## Specifier ({{TASK_ID}}).
Use retrieved skills as procedures for writing and verifying the spec only when their triggers match this task.

Evidence anchoring:
- Anchor every requirement or acceptance criterion in user intent, `brief.md`, existing code/tests, or an observed edge case.
- If a criterion is inferred, label it as an inference and keep it minimal.
- Do not add generic best-practice requirements without evidence that they matter for this task.

Deterministic check registry:
- Number behavior requirements as `R1`, `R2`, ... and acceptance criteria as `CA1`, `CA2`, ...
- Add a required `## Deterministic Check Registry (check_registry)` section to `spec.md`.
- Include at least one check per acceptance criterion. Keep checks cheap and directly tied to the ids they verify.
- Use this exact item format:
  ```markdown
  - id: DC1
    requirement: R1 | CA1 | R1,CA1
    type: command | static_inspection | manual
    target: command, file, function, flow, or artifact to inspect
    command: exact command if `type: command`; `NOT_APPLICABLE` otherwise
    expected: observable pass condition
    evidence_hint: expected file:line, test output, validation output, or observable behavior
  ```
- Do not invent expensive benchmark checks for small tasks; use the smallest deterministic check that would catch failure.
