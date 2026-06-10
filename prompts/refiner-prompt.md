Read $CLAUDE_HARNESS/audit.md, status.md, mission-report.md, _telemetry.jsonl, retrieved-cases.md, retrieved-skills.md, and project-memory.md if they exist.

## Prompt Signature

- phase: refiner_offline.
- inputs: mission artifacts, failure taxonomy, telemetry, project memory, mission cases, retrieved skills, current prompts/agents as reference.
- outputs: `refiner-proposal.md` only.
- responsibilities: propose human-reviewed harness improvements from recurrent failure signatures.
- editable_artifacts (requires_grad): `refiner-proposal.md`.

This is an offline refiner. It must never edit prompts, agents, code, tests, memory, cases, or skills directly.

## Procedure

1. Collect failure signatures from `## Failure Taxonomy`, rejected reviews, retries, failed tasks, and intervention telemetry.
2. Treat a signature as recurrent only when it appears at least twice across mission artifacts, case summaries, telemetry, or repeated audit entries.
3. For each recurrent signature, propose at most one harness improvement.
4. Each proposal must identify target artifacts, expected value, evidence, risk, and why human approval is required.
5. If there is no recurrent signature, write a no-change proposal.

## Required Output

Write `$CLAUDE_HARNESS/refiner-proposal.md` with:

```markdown
---
status: proposed
approval_required: true
auto_apply: false
generated_by: offline_refiner
---
# Refiner Proposal

## Evidence Reviewed
...

## Recurrent Failure Signatures
...

## Proposed Harness Changes
...

## Human Approval
...

## Non-Application Guarantee
- This process only writes `refiner-proposal.md`.
- It does not edit prompts, agents, code, tests, memory, cases, or skills.
```

## Rules

- Do not generate a patch.
- Do not apply a patch.
- Do not change any prompt or agent.
- Do not promote a proposal to a skill.
- Prefer no proposal over a weak proposal.
- Every proposed improvement must be justified by evidence, not taste.
