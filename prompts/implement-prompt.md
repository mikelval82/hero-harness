TASK_ID: {{TASK_ID}}
TASK_TITLE: {{TASK_TITLE}}
TASK_COMPLEXITY: {{TASK_COMPLEXITY}}
TASK_PIPELINE: {{TASK_PIPELINE}}
TASK_COMPLEXITY_REASON: {{TASK_COMPLEXITY_REASON}}

## Prompt Signature

- phase: implement.
- inputs: task id/title, `project-memory.md`, `retrieved-cases.md`, `retrieved-skills.md`, `spec.md`, `plan.md`, `decisions.md`, `context-cold.md`, `context-hot.md`, code graph instructions.
- outputs: task-scoped code/tests, `status.md`, appended `context-hot.md`.
- responsibilities: implement the current task, verify locally, and report files/risks.
- editable_artifacts (requires_grad): task-scoped production files, task-scoped tests, `status.md`, `context-hot.md`.

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

### Plan
{{PLAN}}

### Decisions
{{DECISIONS}}

### Task routing
- complexity: {{TASK_COMPLEXITY}}
- pipeline: {{TASK_PIPELINE}}
- complexity_reason: {{TASK_COMPLEXITY_REASON}}

### Code graph
{{GRAPH_INSTRUCTIONS}}

Append surprises and deltas to context-hot.md under ## Implementer ({{TASK_ID}}).
Create status.md from scratch (do not expect an existing one from planner).
If a retrieved skill applies, follow its procedure and record any relevant verification evidence in status.md. Ignore skills whose triggers do not match the task.
Before implementation, add a `## Routing` section to status.md:
- task_complexity: {{TASK_COMPLEXITY}}
- task_pipeline: {{TASK_PIPELINE}}
- complexity_reason: {{TASK_COMPLEXITY_REASON}}

Evidence anchoring:
- Treat each completed status step as a claim that needs evidence.
- Verify claims with a command result, relevant test, `file:line`, acceptance criterion, or observed behavior.
- If a step cannot be verified, write `NOT_VERIFIED: reason` instead of marking it complete.

Before reporting done, write a `## Self-Verification` section in status.md with:
- tests_run with command and PASS/FAIL/NOT_RUN reason
- deterministic_checks_run with DC ids from `## Deterministic Check Registry`, PASS/FAIL/NOT_RUN, and evidence
- acceptance_criteria_checked with criterion id plus test, `file:line`, or observed behavior
- edge_cases_considered with evidence or `NOT_APPLICABLE: reason`
- files_touched_reviewed with concrete paths
- harness_artifacts_not_written_to_target
- known_risks

If a mission-validate script exists in the project root (mission-validate.cmd, .bat, .ps1, or .sh), execute it before reporting done. List all modified/created files in status.md under a ## Files section, one per line.
