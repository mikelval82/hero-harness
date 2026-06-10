Read all files in $CLAUDE_HARNESS/ (brainstorm.md, tasks.json, spec.md, plan.md, decisions.md, brief.md, project-memory.md, retrieved-skills.md if they exist). This was a {{MODE}} mission (no implementation). Partial harness modes may stop at spec-only or spec+plan; if plan.md or decisions.md do not exist, report them as N/A instead of inventing a plan.

## Prompt Signature

- phase: report_plan.
- inputs: mission analysis artifacts, project memory, retrieved skills, task status, token/cost summary, mode, task, branch, result.
- outputs: `mission-report.md`, updated `project-memory.md` when there are durable learnings, optional verified skills under `generated-skills/`.
- responsibilities: summarize analysis and proposed plan without inventing implementation, preserve reusable repo-specific learnings, and capture verified reusable procedures.
- editable_artifacts (requires_grad): `mission-report.md`, `project-memory.md`, `generated-skills/*.md`.

PROJECT MEMORY (persistent per target project):
{{PROJECT_MEMORY}}

RETRIEVED VERIFIED SKILLS:
{{RETRIEVED_SKILLS}}

{{TASKS_STATUS}}

TOKEN/COST SUMMARY:
{{TOKEN_COST_SUMMARY}}

After writing the report, update $CLAUDE_HARNESS/project-memory.md only if this analysis produced durable, repo-specific learning. Preserve existing useful entries and append concise bullets under the existing headings. Store conventions, validation commands, hidden constraints, or recurring failure modes with evidence from artifacts. Do not store secrets, private conversation, generic advice, or transient branch-only details. If there is no durable learning, leave project-memory.md unchanged.

If this analysis produced a reusable verified procedure, write exactly one markdown skill under `$CLAUDE_HARNESS/generated-skills/<skill-id>.md`. Only create a skill when artifacts show repeated procedural value and evidence from the analysis; do not invent implementation evidence. Do not duplicate an existing retrieved skill. Use the same skill format as retrieved skills: frontmatter with `skill_id`, `name`, `version`, `status: verified`, `source`, `evidence`, `triggers`, then sections `When To Use`, `Procedure`, `Required Verification`, `Evidence`, and `Risks`. If no reusable verified procedure emerged, do not create any file in `generated-skills/`.

Generate a concise analysis report (30-40 lines) and write it to $CLAUDE_HARNESS/mission-report.md with these sections: Objective, Alignment Summary (from brief.md or N/A), Analysis (key findings from brainstorm.md), Tasks (use the TASK STATUS above as source of truth — do NOT invent statuses), Token/Cost Budget (copy TOKEN/COST SUMMARY as-is), Proposed Approach (from spec.md and plan.md if present; use N/A for missing artifacts), Decisions (from decisions.md or N/A), Recommendations (next steps). Task was: {{TASK}}. Branch: {{BRANCH}}. Final result: {{RESULT}}.
