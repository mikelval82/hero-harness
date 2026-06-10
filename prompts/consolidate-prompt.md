Read $CLAUDE_HARNESS/tasks.json.

## Prompt Signature

- phase: consolidate.
- inputs: `tasks.json`, `{{MAX_TASKS}}`.
- outputs: updated `tasks.json`.
- responsibilities: merge redundant pending tasks while preserving completed tasks and schema.
- editable_artifacts (requires_grad): `tasks.json`.

It contains too many tasks. Consolidate them into **at most {{MAX_TASKS}}** tasks by merging related tasks and eliminating redundancies.

Rules:
- Preserve the exact JSON schema: each task must have `id`, `title`, `files`, `complexity`, `complexity_reason`, and `status` fields.
- Merge `files` arrays when combining tasks. Remove duplicate file paths.
- Merge `complexity_reason` values into one concrete reason that explains the final S/M/L route.
- Keep task IDs as simple dotted numbers (e.g. "1", "2", "3" or "1.1", "1.2").
- Preserve any task with `"status": "completed"` unchanged.
- The result must be a valid JSON array.

Write the consolidated array back to $CLAUDE_HARNESS/tasks.json.
