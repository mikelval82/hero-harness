# Review

Spec:
{{SPEC}}

Plan:
{{PLAN}}

Decisions:
{{DECISIONS}}

Approved task contract (authoritative):
{{TASK_CONTRACT}}

Review against every contractual obligation. Any unapproved rename,
relocation, weakening, or removal is blocking.

Run `RunValidation(check_id="target_validation")` before declaring approval.
The runtime records its receipt in `validation-evidence/`; do not replace that
receipt with a claim in the audit.

{{GRAPH_INSTRUCTIONS}}

Review the implementation and write `$CLAUDE_HARNESS/audit.md`.

Required sections:

## Verdict

Use one of: APPROVED, MINOR_CHANGES, CHANGES_REQUESTED.

Required ending:

**STATUS: DONE**
