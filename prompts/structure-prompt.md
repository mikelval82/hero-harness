# Structure

Mission: {{TASK}}

Brainstorm:
{{BRAINSTORM}}

Brief:
{{BRIEF}}

ChangeSet (compiled from the approved design map, if any):
{{CHANGESET}}

Write `$CLAUDE_HARNESS/tasks.json` as a JSON list of objects with id, title, complexity, status, failure_reason, covers, dependencies and target_nodes.

If a ChangeSet is present, you are grouping its operations into deliverable tasks, not inventing the decomposition: every operation id must appear in exactly one task's `covers`; `dependencies` lists ids of tasks that must complete first (respect each operation's depends_on); `target_nodes` lists the design node ids each task touches. A deterministic validator rejects plans with missing, duplicated or unknown coverage, unknown dependencies or cycles. If no ChangeSet is present, covers/dependencies/target_nodes may be empty lists.

