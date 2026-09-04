# Structure

Mission: {{TASK}}

Brainstorm:
{{BRAINSTORM}}

Brief:
{{BRIEF}}

ChangeSet (compiled from the approved design map, if any):
{{CHANGESET}}

Write `$CLAUDE_HARNESS/tasks.json` with the `WriteJson` tool, never with the
generic `Write` tool. The content must be a JSON list of objects with exactly
these required fields: `id`, `title`, `complexity`, `status`, `failure_reason`,
`covers`, `dependencies`, and `target_nodes`. Use `[]` for empty list fields and
an empty string for `failure_reason`.

If a ChangeSet is present, you are grouping its operations into deliverable tasks, not inventing the decomposition: every operation id must appear in exactly one task's `covers`; `dependencies` lists ids of tasks that must complete first (respect each operation's depends_on); `target_nodes` lists the design node ids each task touches. A deterministic validator rejects plans with missing, duplicated or unknown coverage, unknown dependencies or cycles. If no ChangeSet is present, covers/dependencies/target_nodes may be empty lists.
