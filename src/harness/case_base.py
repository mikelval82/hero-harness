from __future__ import annotations

import json
import math
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from src.harness.project_memory import project_memory_dir
from src.harness.tasks import audit_verdict, parse_status_files, task_summary
from src.harness.telemetry import summarize_costs


CASES_FILE = "cases.jsonl"
HARNESS_CASES_FILE = "retrieved-cases.md"
HARNESS_CASES_PATH_FILE = "_project_cases_path"
MAX_EXCERPT_CHARS = 1200


def case_base_path(project_dir: str | Path, *, base_dir: Path | None = None) -> Path:
    return project_memory_dir(project_dir, base_dir=base_dir) / CASES_FILE


def ensure_case_base(project_dir: str | Path, *, base_dir: Path | None = None) -> Path:
    path = case_base_path(project_dir, base_dir=base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        path.write_text("", encoding="utf-8")
    return path


def read_cases(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    cases = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            cases.append(record)
    return cases


def append_case(path: Path, case: dict[str, Any]) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_ids = {c.get("case_id") for c in read_cases(path)}
    if case.get("case_id") in existing_ids:
        return False
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(case, ensure_ascii=True, sort_keys=True) + "\n")
    return True


def _read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _excerpt(text: str, max_chars: int = MAX_EXCERPT_CHARS) -> str:
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    compact = "\n".join(lines)
    if len(compact) <= max_chars:
        return compact
    return compact[:max_chars].rstrip() + "\n...[truncated]"


def _tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-zA-Z0-9_]{3,}", text.lower())}


def _similarity(query: str, text: str) -> float:
    query_tokens = _tokenize(query)
    text_tokens = _tokenize(text)
    if not query_tokens or not text_tokens:
        return 0.0
    overlap = len(query_tokens & text_tokens)
    return overlap / math.sqrt(len(query_tokens) * len(text_tokens))


def retrieve_cases(
    cases_path: Path,
    query: str,
    *,
    top_k: int = 3,
    min_score: float = 0.05,
) -> list[dict[str, Any]]:
    scored = []
    for case in read_cases(cases_path):
        searchable = "\n".join(
            str(case.get(key, ""))
            for key in (
                "retrieval_text",
                "task",
                "brief_summary",
                "spec_summary",
                "plan_summary",
                "lessons",
            )
        )
        score = _similarity(query, searchable)
        if score >= min_score:
            item = dict(case)
            item["similarity_score"] = round(score, 4)
            scored.append(item)
    scored.sort(key=lambda c: c.get("similarity_score", 0), reverse=True)
    return scored[:top_k]


def format_retrieved_cases(cases: list[dict[str, Any]]) -> str:
    if not cases:
        return (
            "# Retrieved Mission Cases\n\n"
            "No similar approved mission cases found for this project.\n"
        )

    sections = ["# Retrieved Mission Cases", ""]
    for idx, case in enumerate(cases, start=1):
        files = ", ".join(case.get("files_changed") or []) or "none"
        lessons = case.get("lessons") or []
        if isinstance(lessons, list):
            lesson_text = "; ".join(str(item) for item in lessons[:5]) or "none"
        else:
            lesson_text = str(lessons)
        validation = case.get("validation_summary") or "not recorded"
        sections.extend([
            f"## Case {idx}: {case.get('task', 'untitled')}",
            f"- case_id: {case.get('case_id', 'unknown')}",
            f"- similarity_score: {case.get('similarity_score', 0)}",
            f"- mode: {case.get('mode', 'unknown')}",
            f"- outcome: {case.get('outcome', 'unknown')}",
            f"- files_changed: {files}",
            f"- validation: {validation}",
            f"- lessons: {lesson_text}",
            "",
            "### Plan Summary",
            case.get("plan_summary") or "not recorded",
            "",
            "### Audit Summary",
            case.get("audit_summary") or "not recorded",
            "",
        ])
    return "\n".join(sections).rstrip() + "\n"


def stage_retrieved_cases(
    project_dir: str | Path,
    harness: Path,
    *,
    query: str,
    base_dir: Path | None = None,
    preserve_existing: bool = False,
    top_k: int = 3,
) -> dict[str, Path]:
    cases_path = ensure_case_base(project_dir, base_dir=base_dir)
    staged = harness / HARNESS_CASES_FILE
    if not preserve_existing or not staged.is_file():
        retrieved = retrieve_cases(cases_path, query, top_k=top_k)
        staged.write_text(format_retrieved_cases(retrieved), encoding="utf-8")
    (harness / HARNESS_CASES_PATH_FILE).write_text(str(cases_path), encoding="utf-8")
    return {"persistent": cases_path, "staged": staged}


def _tasks_all_completed(harness: Path) -> bool:
    tasks_path = harness / "tasks.json"
    if not tasks_path.is_file():
        return False
    try:
        tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    if not isinstance(tasks, list) or not tasks:
        return False
    return all(isinstance(t, dict) and t.get("status") == "completed" for t in tasks)


def _validation_summary(status: str, audit: str) -> str:
    source = "\n".join([status, audit])
    matches = [
        line.strip()
        for line in source.splitlines()
        if any(marker in line.lower() for marker in ("pytest", "mission-validate", "pass", "fail", "not_run"))
    ]
    return _excerpt("\n".join(matches), max_chars=500) if matches else "not recorded"


def _lessons_from_artifacts(report: str, audit: str, decisions: str) -> list[str]:
    candidates = []
    for text in (report, audit, decisions):
        for line in text.splitlines():
            stripped = line.strip().lstrip("-").strip()
            if not stripped:
                continue
            lowered = stripped.lower()
            if any(term in lowered for term in ("decision", "risk", "failure", "gotcha", "constraint", "validation")):
                candidates.append(stripped)
            if len(candidates) >= 5:
                return candidates
    return candidates


def build_mission_case(
    harness: Path,
    *,
    task: str,
    branch: str,
    mode: str,
    project_dir: str | Path,
) -> dict[str, Any]:
    brief = _read_text(harness / "brief.md")
    spec = _read_text(harness / "spec.md")
    plan = _read_text(harness / "plan.md")
    decisions = _read_text(harness / "decisions.md")
    status = _read_text(harness / "status.md")
    audit = _read_text(harness / "audit.md")
    report = _read_text(harness / "mission-report.md")
    files_changed = parse_status_files(harness)
    created_at = datetime.now().isoformat(timespec="seconds")
    case_id = str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"{Path(project_dir).resolve()}|{branch}|{task}|{_excerpt(report, 300)}",
    ))

    retrieval_text = "\n".join([
        task,
        brief,
        spec,
        plan,
        decisions,
        audit,
        report,
        " ".join(files_changed),
    ])

    return {
        "case_id": case_id,
        "created_at": created_at,
        "project": Path(project_dir).resolve().name,
        "project_dir": str(Path(project_dir).resolve()),
        "task": task,
        "branch": branch,
        "mode": mode,
        "outcome": "APPROVED",
        "task_summary": task_summary(harness),
        "brief_summary": _excerpt(brief),
        "spec_summary": _excerpt(spec),
        "plan_summary": _excerpt(plan),
        "decisions_summary": _excerpt(decisions),
        "files_changed": files_changed,
        "audit_verdict": audit_verdict(harness),
        "audit_summary": _excerpt(audit),
        "report_summary": _excerpt(report),
        "validation_summary": _validation_summary(status, audit),
        "telemetry": summarize_costs(harness),
        "lessons": _lessons_from_artifacts(report, audit, decisions),
        "retrieval_text": _excerpt(retrieval_text, max_chars=4000),
    }


def save_approved_mission_case(
    harness: Path,
    *,
    task: str,
    branch: str,
    mode: str,
    project_dir: str | Path,
    blocked: Any,
) -> bool:
    if getattr(blocked, "reason", None):
        return False
    if not _tasks_all_completed(harness):
        return False
    verdict = audit_verdict(harness)
    if verdict not in {"APPROVED", "UNKNOWN"}:
        return False
    pointer = harness / HARNESS_CASES_PATH_FILE
    if not pointer.is_file():
        return False
    raw_path = pointer.read_text(encoding="utf-8").strip()
    if not raw_path:
        return False
    case = build_mission_case(harness, task=task, branch=branch, mode=mode, project_dir=project_dir)
    return append_case(Path(raw_path), case)
