TASK: {{TASK}}

## Prompt Signature

- phase: grill.
- inputs: `{{TASK}}`, `project-memory.md`, `retrieved-cases.md`, `retrieved-skills.md`, `brainstorm.md`, `tasks.json`, code graph instructions.
- outputs: `brief.md`.
- responsibilities: clarify intent, scope, constraints, and decisions with the user.
- editable_artifacts (requires_grad): `brief.md`.

## Prior context (pre-loaded)

### Project memory (persistent per target project)
{{PROJECT_MEMORY}}

### Similar approved mission cases
{{MISSION_CASES}}

### Retrieved verified skills
{{RETRIEVED_SKILLS}}

### Research findings (challenge these)
{{BRAINSTORM}}

### Proposed task breakdown (challenge scope and priorities)
{{TASKS}}

{{GRAPH_INSTRUCTIONS}}

Use Read, Grep, Glob, and the code graph CLI to verify your assumptions against the actual codebase before asking the user.

When the user says /done, write brief.md to $CLAUDE_HARNESS following your protocol.
