TASK: {{TASK}}

## Prompt Signature

- phase: structure.
- inputs: `{{TASK}}`, `project-memory.md`, `retrieved-cases.md`, `retrieved-skills.md`, `brainstorm.md`, optional `brief.md`.
- outputs: `tasks.json`.
- responsibilities: convert research into ordered executable tasks with files, complexity, complexity_reason, and status.
- editable_artifacts (requires_grad): `tasks.json`.

## Brainstorm results (pre-loaded)

{{BRAINSTORM}}

## Project memory (persistent per target project)

{{PROJECT_MEMORY}}

## Similar approved mission cases

{{MISSION_CASES}}

## Retrieved verified skills

{{RETRIEVED_SKILLS}}

Use project memory only to preserve repo-specific conventions, known constraints, and repeated failure modes. Do not create tasks solely because memory mentions a historical issue.
Use retrieved cases only to inform task ordering, likely files, and validation patterns when the current mission is genuinely similar.
Use retrieved skills only as procedural guidance for task shape and verification when the trigger matches this mission.

## Mission brief (alignment from grill)

{{BRIEF}}

Complexity routing:
- Every task in `tasks.json` must include `complexity` and `complexity_reason`.
- Use `S` only for small, low-risk, well-scoped edits where implement-only is enough.
- Use `M` for normal tasks that need spec, plan, implementation, and review.
- Use `L` for broad, risky, or multi-step tasks that need burst implementation.
- `complexity_reason` must explain the route choice using scope, risk, files, dependencies, tests, uncertainty, or user constraints. Do not write generic reasons like "seems medium".
