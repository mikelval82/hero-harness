# Implement Burst

Task: {{TASK_ID}} {{TASK_TITLE}}

Step:
{{PLAN_STEP}}

Progress:
{{PROGRESS}}

Spec:
{{SPEC}}

Decisions:
{{DECISIONS}}

Approved task contract (authoritative):
{{TASK_CONTRACT}}

Keep every burst within this contract. Do not rename, relocate, weaken, or
remove an obligation without requesting a design amendment.

If implementation reveals a required design change, use GraphQuery and then
GraphPropose with an atomic, evidence-backed update. Execution will pause at a
safe boundary for human amendment review; do not silently apply that change.

{{GRAPH_INSTRUCTIONS}}

{{BURST_FINAL_INSTRUCTIONS}}

Update `$CLAUDE_HARNESS/_burst_progress.md`. On the final burst, write `$CLAUDE_HARNESS/status.md`.

Required ending for final status:

**STATUS: DONE**
