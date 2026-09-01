from __future__ import annotations

import re
from pathlib import Path


class ReviewVerdict:
    APPROVED = "APPROVED"
    MINOR_CHANGES = "MINOR_CHANGES"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    UNKNOWN = "UNKNOWN"


FILES_HEADING_RE = re.compile(r"^##\s+(Files|Archivos)\b", re.IGNORECASE)
HEADING_RE = re.compile(r"^##\s+")
PATH_TOKEN_RE = re.compile(r"`([^`]+)`|[-*]\s+(.+)$")


def audit_verdict(text: str) -> str:
    upper = text.upper()
    if "CHANGES_REQUESTED" in upper or "CHANGES REQUESTED" in upper:
        return ReviewVerdict.CHANGES_REQUESTED
    if "MINOR_CHANGES" in upper or "MINOR CHANGES" in upper:
        return ReviewVerdict.MINOR_CHANGES
    if "APPROVED" in upper or "APROBADO" in upper:
        return ReviewVerdict.APPROVED
    return ReviewVerdict.UNKNOWN


def status_files(text: str) -> list[Path]:
    in_files = False
    paths: list[Path] = []
    for line in text.splitlines():
        if FILES_HEADING_RE.match(line.strip()):
            in_files = True
            continue
        if in_files and HEADING_RE.match(line.strip()):
            break
        if not in_files:
            continue
        match = PATH_TOKEN_RE.search(line.strip())
        if not match:
            continue
        candidate = (match.group(1) or match.group(2) or "").strip()
        candidate = candidate.strip("-* `")
        if not candidate or candidate.startswith("#"):
            continue
        paths.append(Path(candidate))
    return paths


def report_preview(text: str, *, max_lines: int = 60) -> str:
    return "\n".join(text.splitlines()[:max_lines])

