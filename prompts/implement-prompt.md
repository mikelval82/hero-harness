# Implement

Task: {{TASK_ID}} {{TASK_TITLE}}

Spec:
{{SPEC}}

Plan:
{{PLAN}}

Decisions:
{{DECISIONS}}

Context:
{{CONTEXT_COLD}}

{{CONTEXT_HOT}}

Approved task contract (authoritative):
{{TASK_CONTRACT}}

Implement every contractual obligation. Do not rename, relocate, weaken, or
remove one without requesting a design amendment.

If implementation reveals that the approved design itself must change, first use
GraphQuery and then GraphPropose with one atomic, evidence-backed update. This
automatically pauses execution at the next safe boundary for human amendment
review; do not silently implement the unapproved alternative.

{{GRAPH_INSTRUCTIONS}}

Implement the task in the project directory. Then write `$CLAUDE_HARNESS/status.md`.

Required sections:

## Files

Required ending:

**STATUS: DONE**
