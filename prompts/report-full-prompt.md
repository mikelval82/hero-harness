Read all files in $CLAUDE_HARNESS/ (brainstorm.md, tasks.json, spec.md, plan.md, decisions.md, status.md, audit.md, brief.md, project-memory.md, retrieved-skills.md if they exist).

## Prompt Signature

- phase: report.
- inputs: mission artifacts, project memory, retrieved skills, task status, token/cost summary, git evidence, diff stat, task, branch, result.
- outputs: `mission-report.md`, updated `project-memory.md` when there are durable learnings, optional verified skills under `generated-skills/`.
- responsibilities: summarize actual completed work from artifacts and git evidence, preserve reusable repo-specific learnings, and capture verified reusable procedures.
- editable_artifacts (requires_grad): `mission-report.md`, `project-memory.md`, `generated-skills/*.md`.

PROJECT MEMORY (persistent per target project):
{{PROJECT_MEMORY}}

RETRIEVED VERIFIED SKILLS:
{{RETRIEVED_SKILLS}}

{{TASKS_STATUS}}

TOKEN/COST SUMMARY:
{{TOKEN_COST_SUMMARY}}

GIT EVIDENCE (commits on this branch vs master):
{{GIT_EVIDENCE}}

GIT DIFF STAT:
{{GIT_DIFF_STAT}}

IMPORTANT: Use the TASK STATUS and GIT EVIDENCE above as source of truth. Do NOT invent or assume task completions — if tasks.json says pending, they are pending. If there are no commits, no code was changed. Cross-check: each completed task should have a corresponding commit.

Generate a concise mission report (30-40 lines) and write it to $CLAUDE_HARNESS/mission-report.md with these sections: Objective, Alignment Summary (from brief.md or N/A), Tasks Summary (from TASK STATUS above - copy as-is), Token/Cost Budget (copy TOKEN/COST SUMMARY as-is), Changes Made (from GIT EVIDENCE - actual commits and files changed), Decisions Taken (from decisions.md), Unresolved Issues (any BLOCKED/failed/pending items), Validation Results (mission-validate result + review verdict). Task was: {{TASK}}. Branch: {{BRANCH}}. Final result: {{RESULT}}.

After writing the report, update $CLAUDE_HARNESS/project-memory.md only if this mission produced durable, repo-specific learning. Preserve existing useful entries and append concise bullets under the existing headings. Store conventions, validation commands that actually worked, hidden constraints, and recurring failure modes with evidence from artifacts/tests. Do not store secrets, private conversation, generic advice, or transient branch-only details. If there is no durable learning, leave project-memory.md unchanged.

If this mission produced a reusable verified procedure, write exactly one markdown skill under `$CLAUDE_HARNESS/generated-skills/<skill-id>.md`. Only create a skill when artifacts show repeated procedural value and verification evidence from tests, audit, or mission result. Do not duplicate an existing retrieved skill. Use this format:

```markdown
---
skill_id: short-kebab-case-id
name: Human Readable Name
version: 1
status: verified
source: mission-report
evidence: task/status/audit/test evidence
triggers:
  - trigger phrase
---
# Human Readable Name

## When To Use
...

## Procedure
1. ...

## Required Verification
- ...

## Evidence
- ...

## Risks
- ...
```

If no reusable verified procedure emerged, do not create any file in `generated-skills/`.
