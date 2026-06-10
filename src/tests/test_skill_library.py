from src.harness.skill_library import (
    DEFAULT_SKILL_ID,
    HARNESS_GENERATED_SKILLS_DIR,
    HARNESS_SKILLS_FILE,
    HARNESS_SKILLS_PATH_FILE,
    ensure_skill_library,
    format_retrieved_skills,
    read_skill_index,
    retrieve_skills,
    stage_retrieved_skills,
    sync_generated_skills,
)


def test_seed_default_skill_creates_prompt_gate_contract_skill(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    info = ensure_skill_library(project, base_dir=tmp_path / "memory")

    skill_file = info["skills_dir"] / f"{DEFAULT_SKILL_ID}.md"
    records = read_skill_index(info["index"])

    assert skill_file.is_file()
    assert DEFAULT_SKILL_ID in skill_file.read_text(encoding="utf-8")
    assert any(record["skill_id"] == DEFAULT_SKILL_ID for record in records)


def test_retrieve_skills_returns_relevant_verified_skill(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    info = ensure_skill_library(project, base_dir=tmp_path / "memory")

    retrieved = retrieve_skills(info["index"], "update prompt contract gate marker and phase include")

    assert retrieved
    assert retrieved[0]["skill_id"] == DEFAULT_SKILL_ID
    assert "Prompt/Gate Contract Change" in retrieved[0]["content"]


def test_format_retrieved_skills_empty():
    text = format_retrieved_skills([])

    assert "Retrieved Verified Skills" in text
    assert "No relevant verified skills" in text


def test_stage_retrieved_skills_writes_markdown_pointer_and_generated_dir(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    harness = tmp_path / "harness"
    harness.mkdir()

    info = stage_retrieved_skills(
        project,
        harness,
        query="prompt contract gate marker",
        base_dir=tmp_path / "memory",
    )

    staged = harness / HARNESS_SKILLS_FILE
    pointer = harness / HARNESS_SKILLS_PATH_FILE
    generated = harness / HARNESS_GENERATED_SKILLS_DIR

    assert staged.is_file()
    assert DEFAULT_SKILL_ID in staged.read_text(encoding="utf-8")
    assert pointer.read_text(encoding="utf-8") == str(info["persistent"])
    assert generated.is_dir()


def test_sync_generated_skills_copies_verified_skill_and_updates_index(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    harness = tmp_path / "harness"
    harness.mkdir()
    info = stage_retrieved_skills(
        project,
        harness,
        query="diagnostic retry",
        base_dir=tmp_path / "memory",
    )
    generated = harness / HARNESS_GENERATED_SKILLS_DIR
    generated_skill = generated / "diagnostic-retry.md"
    generated_skill.write_text(
        """---
skill_id: diagnostic-retry
name: Diagnostic Retry
version: 1
status: verified
source: mission-report
evidence: audit.md rejected root cause and retry tests passed
triggers:
  - retry after failed review
---
# Diagnostic Retry

## When To Use
Use when a review rejects an implementation and the retry must preserve scope.

## Procedure
1. Write a diagnosis before editing.
2. Tie the fix to the failed check and acceptance criterion.

## Required Verification
- Run the failed deterministic check again.

## Evidence
- audit.md and status.md.

## Risks
- Retry drift outside the reviewed failure.
""",
        encoding="utf-8",
    )

    saved = sync_generated_skills(harness)

    records = read_skill_index(info["index"])
    persistent_skill = info["persistent"] / "diagnostic-retry.md"
    retrieved = retrieve_skills(info["index"], "retry after failed review diagnosis")

    assert saved == 1
    assert persistent_skill.is_file()
    assert any(record["skill_id"] == "diagnostic-retry" for record in records)
    assert retrieved[0]["skill_id"] == "diagnostic-retry"
