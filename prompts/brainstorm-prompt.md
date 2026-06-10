TASK: {{TASK}}

## Prompt Signature

- phase: research.
- inputs: `{{TASK}}`, `project-memory.md`, `retrieved-cases.md`, `retrieved-skills.md`, code graph instructions, target codebase.
- outputs: `brainstorm.md`, `context-hot.md`.
- responsibilities: investigate approaches and record verifiable codebase facts.
- editable_artifacts (requires_grad): `brainstorm.md`, `context-hot.md`.

Do NOT generate sprint.md. Generate only: brainstorm.md, context-hot.md.

## Project memory (persistent per target project)

{{PROJECT_MEMORY}}

## Similar approved mission cases

{{MISSION_CASES}}

## Retrieved verified skills

{{RETRIEVED_SKILLS}}

Use project memory as prior evidence, not as authority. Re-verify stale or risky facts against the current codebase before relying on them.
Use retrieved mission cases as concrete examples of prior successful work in this repo. Borrow patterns only when current codebase evidence still supports them.
Use retrieved verified skills as reusable procedures only when their triggers match the current mission. Ignore non-applicable skills and still verify against current code.

{{GRAPH_INSTRUCTIONS}}
