Read $CLAUDE_HARNESS/context-hot.md.

## Prompt Signature

- phase: compact.
- inputs: `context-hot.md`, task id/title.
- outputs: `_compact_tmp.md`.
- responsibilities: compress current findings into durable verifiable facts.
- editable_artifacts (requires_grad): `_compact_tmp.md`.

Compress its contents into a concise summary (max 20 lines) preserving ONLY:
- File paths and key code locations discovered
- Patterns and architectural insights
- Gotchas, constraints, edge cases
- Test results (pass/fail, what broke)

Discard: verbose descriptions, full code snippets, exploratory dead-ends.

Write the summary to $CLAUDE_HARNESS/_compact_tmp.md in this exact format:

### {{TASK_ID}}: {{TASK_TITLE}}
- fact 1
- fact 2
...
