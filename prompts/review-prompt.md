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

Also write `$CLAUDE_HARNESS/review-evidence.json` (schema version 1). It is a
typed assessment, not a restatement of the audit:

```json
{
  "schema_version": 1,
  "claims": [{"id": "C1", "statement": "claim", "status": "supported", "evidence_refs": ["src/file.py:12"]}],
  "checks": [
    {"id": "hardcoding", "status": "pass", "evidence_refs": ["src/file.py:12"]},
    {"id": "special_casing", "status": "pass", "evidence_refs": ["tests/test_file.py:9"]},
    {"id": "scope", "status": "pass", "evidence_refs": ["status.md"]}
  ],
  "failures": []
}
```

For an approved review, every claim must be `supported`, all three checks must
be `pass`, and `failures` must be empty. Otherwise use `fail` or `not_run` and
include at least one failure with `failure_type`,
`recoverability_lost_at_stage`, and `evidence_refs`.

Required sections:

## Verdict

Use one of: APPROVED, MINOR_CHANGES, CHANGES_REQUESTED.

Required ending:

**STATUS: DONE**
