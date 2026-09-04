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

Also write `$CLAUDE_HARNESS/review-evidence.json` with the `WriteJson` tool,
never with the generic `Write` tool (the tool validates the JSON before saving).
It must have schema version 1. It is a
typed assessment, not a restatement of the audit:

The JSON is validated strictly. The `checks` array must contain exactly these
three ids, once each: `hardcoding`, `special_casing`, and `scope`; do not add
any other check ids. For every item in `failures`, `failure_type` must be one
of: `technical_bug`, `spec_mismatch`, `semantic_mismatch`,
`evaluation_hacking`, `unclear_requirement`, `over_scoping`, `missing_test`,
or `context_loss`. `recoverability_lost_at_stage` must be one of: `research`,
`grill`, `spec`, `plan`, `implement`, `implement_bursts`, `review`,
`reimplement`, `user_input`, or `unknown`. Do not invent variants such as
`contract_violation`, `bounded_grammar_divergence`, or task-specific stage
names. Put additional technical categories in the failure `description`, not
in `failure_type`. Every failure object must contain all four required fields:
`id` (for example `F1`), `failure_type`, `recoverability_lost_at_stage`, and a
non-empty `evidence_refs` array. If there are no failures, write
`"failures": []`; never write a failure without an id. The same rule applies
to claims: every claim needs `id`, `statement`, `status`, and non-empty
`evidence_refs`.

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

Before finishing, validate the JSON mentally against the rules above: exactly
three checks, no extra check ids, and every failure uses only the enumerated
`failure_type` and `recoverability_lost_at_stage` values; every failure has an
`id` and non-empty `evidence_refs`; every claim has an `id` and non-empty
`evidence_refs`.
