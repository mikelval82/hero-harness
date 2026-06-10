from __future__ import annotations

import json
import math
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from src.harness.project_memory import project_memory_dir


SKILLS_DIR = "skills"
SKILL_INDEX_FILE = "skills.jsonl"
HARNESS_SKILLS_FILE = "retrieved-skills.md"
HARNESS_SKILLS_PATH_FILE = "_project_skills_path"
HARNESS_GENERATED_SKILLS_DIR = "generated-skills"
MAX_SKILL_EXCERPT_CHARS = 1800

DEFAULT_SKILL_ID = "prompt-gate-contract-change"
DEFAULT_SKILL_FILE = f"{DEFAULT_SKILL_ID}.md"


DEFAULT_SKILL_TEXT = """---
skill_id: prompt-gate-contract-change
name: Prompt/Gate Contract Change
version: 1
status: verified
source: seed
evidence: tasks 8, 13, 14, 15 in research_plan/checkpoints.md
triggers:
  - prompt contract
  - gate marker
  - phase include
  - agent signature
  - deterministic check
---
# Prompt/Gate Contract Change

## When To Use

Use this skill when a task changes the information contract between agents,
prompts, gates, staged harness artifacts, or deterministic checks.

## Procedure

1. Identify the new artifact or field and decide whether it is read-only context
   or an editable output.
2. Add the staged artifact in `setup_harness(...)` if it must exist before phases
   run.
3. Add the include to `PHASE_REGISTRY` for every phase that should receive it.
4. Update prompt signatures so inputs, outputs, responsibilities, and
   `editable_artifacts (requires_grad)` match the new contract.
5. Update agent signatures and protocol text so agents know whether the artifact
   is evidence, a procedure, or an output they may edit.
6. Add or adjust gate checks only when the artifact is a required output.
7. Add focused tests for setup, include injection, prompt contracts, and runner
   sync behavior.
8. Update the research_plan checkpoint with files changed, verification commands,
   evidence, and residual risks.

## Required Verification

- `src/tests/test_context.py` for phase include wiring.
- `src/tests/test_prompt_contracts.py` for prompt and agent contract drift.
- A setup or runner test when the artifact is staged or synchronized.
- A gate test when a required markdown section or field is enforced.

## Evidence

This pattern was verified by the project-memory, mission case-base, deterministic
check registry, and prompt signature tasks recorded in
`research_plan/checkpoints.md`.

## Risks

- Adding an include without prompt text creates invisible context that agents may
  ignore.
- Adding prompt text without tests allows future contract drift.
- Treating retrieved context as authority can import stale behavior; agents must
  still verify against current code.
"""


def skill_library_dir(project_dir: str | Path, *, base_dir: Path | None = None) -> Path:
    return project_memory_dir(project_dir, base_dir=base_dir) / SKILLS_DIR


def skill_index_path(project_dir: str | Path, *, base_dir: Path | None = None) -> Path:
    return project_memory_dir(project_dir, base_dir=base_dir) / SKILL_INDEX_FILE


def _tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-zA-Z0-9_]{3,}", text.lower())}


def _similarity(query: str, text: str) -> float:
    query_tokens = _tokenize(query)
    text_tokens = _tokenize(text)
    if not query_tokens or not text_tokens:
        return 0.0
    overlap = len(query_tokens & text_tokens)
    return overlap / math.sqrt(len(query_tokens) * len(text_tokens))


def _excerpt(text: str, max_chars: int = MAX_SKILL_EXCERPT_CHARS) -> str:
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    compact = "\n".join(lines)
    if len(compact) <= max_chars:
        return compact
    return compact[:max_chars].rstrip() + "\n...[truncated]"


def _sanitize_skill_id(value: str) -> str:
    base = value.strip().lower().replace("_", "-").replace(" ", "-")
    safe = "".join(ch for ch in base if ch.isalnum() or ch == "-")
    return re.sub(r"-{2,}", "-", safe).strip("-") or "skill"


def parse_skill_metadata(text: str) -> dict[str, Any]:
    if not text.startswith("---"):
        return {}
    lines = text.splitlines()
    if len(lines) < 3 or lines[0].strip() != "---":
        return {}
    try:
        end = next(i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration:
        return {}

    metadata: dict[str, Any] = {}
    current_list_key: str | None = None
    for line in lines[1:end]:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- ") and current_list_key:
            value = stripped[2:].strip().strip('"')
            if value:
                metadata.setdefault(current_list_key, []).append(value)
            continue
        if ":" not in line:
            current_list_key = None
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip('"')
        if value:
            metadata[key] = value
            current_list_key = None
        else:
            metadata[key] = []
            current_list_key = key
    return metadata


def _heading(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return ""


def _relative_skill_path(skills_dir: Path, skill_file: Path) -> str:
    try:
        return str(skill_file.relative_to(skills_dir.parent)).replace("\\", "/")
    except ValueError:
        return skill_file.name


def _skill_path_from_record(index_path: Path, record: dict[str, Any]) -> Path:
    raw = str(record.get("path") or "")
    if not raw:
        return index_path.parent / SKILLS_DIR / f"{record.get('skill_id', 'skill')}.md"
    path = Path(raw)
    if path.is_absolute():
        return path
    return index_path.parent / path


def _skill_record_from_file(
    skill_file: Path,
    *,
    skills_dir: Path,
    source: str | None = None,
) -> dict[str, Any]:
    text = skill_file.read_text(encoding="utf-8", errors="replace")
    metadata = parse_skill_metadata(text)
    skill_id = _sanitize_skill_id(str(metadata.get("skill_id") or skill_file.stem))
    name = str(metadata.get("name") or _heading(text) or skill_id)
    triggers = metadata.get("triggers") or []
    if not isinstance(triggers, list):
        triggers = [str(triggers)]
    status = str(metadata.get("status") or "verified").lower()
    source_value = source or str(metadata.get("source") or "mission-report")
    retrieval_text = "\n".join([
        skill_id,
        name,
        " ".join(str(item) for item in triggers),
        str(metadata.get("evidence") or ""),
        text,
    ])
    return {
        "skill_id": skill_id,
        "name": name,
        "version": str(metadata.get("version") or "1"),
        "status": status,
        "source": source_value,
        "evidence": str(metadata.get("evidence") or ""),
        "triggers": [str(item) for item in triggers],
        "summary": _excerpt(text, max_chars=500),
        "path": _relative_skill_path(skills_dir, skill_file),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "retrieval_text": _excerpt(retrieval_text, max_chars=4000),
    }


def read_skill_index(index_path: Path) -> list[dict[str, Any]]:
    if not index_path.is_file():
        return []
    records = []
    for line in index_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def write_skill_index(index_path: Path, records: list[dict[str, Any]]) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with open(index_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n")


def upsert_skill_record(index_path: Path, record: dict[str, Any]) -> bool:
    records = read_skill_index(index_path)
    skill_id = record.get("skill_id")
    replaced = False
    updated = []
    for existing in records:
        if existing.get("skill_id") == skill_id:
            updated.append(record)
            replaced = True
        else:
            updated.append(existing)
    if not replaced:
        updated.append(record)
    write_skill_index(index_path, updated)
    return not replaced


def ensure_skill_library(project_dir: str | Path, *, base_dir: Path | None = None) -> dict[str, Path]:
    skills_dir = skill_library_dir(project_dir, base_dir=base_dir)
    index_path = skill_index_path(project_dir, base_dir=base_dir)
    skills_dir.mkdir(parents=True, exist_ok=True)
    if not index_path.is_file():
        index_path.write_text("", encoding="utf-8")
    seed_default_skills(project_dir, base_dir=base_dir)
    return {"skills_dir": skills_dir, "index": index_path}


def seed_default_skills(project_dir: str | Path, *, base_dir: Path | None = None) -> Path:
    skills_dir = skill_library_dir(project_dir, base_dir=base_dir)
    index_path = skill_index_path(project_dir, base_dir=base_dir)
    skills_dir.mkdir(parents=True, exist_ok=True)
    if not index_path.is_file():
        index_path.write_text("", encoding="utf-8")
    skill_file = skills_dir / DEFAULT_SKILL_FILE
    if not skill_file.is_file():
        skill_file.write_text(DEFAULT_SKILL_TEXT, encoding="utf-8")
    existing_ids = {record.get("skill_id") for record in read_skill_index(index_path)}
    if DEFAULT_SKILL_ID not in existing_ids:
        record = _skill_record_from_file(skill_file, skills_dir=skills_dir, source="seed")
        upsert_skill_record(index_path, record)
    return skill_file


def retrieve_skills(
    index_path: Path,
    query: str,
    *,
    top_k: int = 3,
    min_score: float = 0.05,
) -> list[dict[str, Any]]:
    scored = []
    for record in read_skill_index(index_path):
        if str(record.get("status", "")).lower() != "verified":
            continue
        skill_text = ""
        skill_file = _skill_path_from_record(index_path, record)
        if skill_file.is_file():
            skill_text = skill_file.read_text(encoding="utf-8", errors="replace")
        searchable = "\n".join([
            str(record.get("retrieval_text", "")),
            str(record.get("name", "")),
            " ".join(str(item) for item in record.get("triggers") or []),
            skill_text,
        ])
        score = _similarity(query, searchable)
        if score >= min_score:
            item = dict(record)
            item["similarity_score"] = round(score, 4)
            item["content"] = _excerpt(skill_text)
            scored.append(item)
    scored.sort(key=lambda item: item.get("similarity_score", 0), reverse=True)
    return scored[:top_k]


def format_retrieved_skills(skills: list[dict[str, Any]]) -> str:
    if not skills:
        return (
            "# Retrieved Verified Skills\n\n"
            "No relevant verified skills found for this project.\n"
        )

    sections = ["# Retrieved Verified Skills", ""]
    for idx, skill in enumerate(skills, start=1):
        triggers = ", ".join(str(item) for item in skill.get("triggers") or []) or "none"
        sections.extend([
            f"## Skill {idx}: {skill.get('name', 'untitled')}",
            f"- skill_id: {skill.get('skill_id', 'unknown')}",
            f"- similarity_score: {skill.get('similarity_score', 0)}",
            f"- status: {skill.get('status', 'unknown')}",
            f"- source: {skill.get('source', 'unknown')}",
            f"- triggers: {triggers}",
            f"- evidence: {skill.get('evidence') or 'not recorded'}",
            "",
            "### Procedure",
            skill.get("content") or skill.get("summary") or "not recorded",
            "",
        ])
    return "\n".join(sections).rstrip() + "\n"


def stage_retrieved_skills(
    project_dir: str | Path,
    harness: Path,
    *,
    query: str,
    base_dir: Path | None = None,
    preserve_existing: bool = False,
    top_k: int = 3,
) -> dict[str, Path]:
    info = ensure_skill_library(project_dir, base_dir=base_dir)
    skills_dir = info["skills_dir"]
    index_path = info["index"]
    staged = harness / HARNESS_SKILLS_FILE
    generated = harness / HARNESS_GENERATED_SKILLS_DIR
    generated.mkdir(parents=True, exist_ok=True)
    if not preserve_existing or not staged.is_file():
        retrieved = retrieve_skills(index_path, query, top_k=top_k)
        staged.write_text(format_retrieved_skills(retrieved), encoding="utf-8")
    (harness / HARNESS_SKILLS_PATH_FILE).write_text(str(skills_dir), encoding="utf-8")
    return {"persistent": skills_dir, "index": index_path, "staged": staged, "generated": generated}


def sync_generated_skills(harness: Path) -> int:
    generated = harness / HARNESS_GENERATED_SKILLS_DIR
    pointer = harness / HARNESS_SKILLS_PATH_FILE
    if not generated.is_dir() or not pointer.is_file():
        return 0
    raw_skills_dir = pointer.read_text(encoding="utf-8").strip()
    if not raw_skills_dir:
        return 0

    skills_dir = Path(raw_skills_dir)
    index_path = skills_dir.parent / SKILL_INDEX_FILE
    skills_dir.mkdir(parents=True, exist_ok=True)
    if not index_path.is_file():
        index_path.write_text("", encoding="utf-8")

    saved = 0
    for generated_file in sorted(generated.glob("*.md")):
        text = generated_file.read_text(encoding="utf-8", errors="replace")
        metadata = parse_skill_metadata(text)
        if str(metadata.get("status", "")).lower() != "verified":
            continue
        skill_id = _sanitize_skill_id(str(metadata.get("skill_id") or generated_file.stem))
        persistent_file = skills_dir / f"{skill_id}.md"
        shutil.copy2(generated_file, persistent_file)
        record = _skill_record_from_file(persistent_file, skills_dir=skills_dir)
        upsert_skill_record(index_path, record)
        saved += 1
    return saved
