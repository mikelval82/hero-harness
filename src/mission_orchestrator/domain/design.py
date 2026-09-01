from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Provenance(Enum):
    ANALYZER = "ANALYZER"
    HUMAN = "HUMAN"
    AGENT = "AGENT"


class Location(Enum):
    IN_REPOSITORY = "IN_REPOSITORY"
    EXTERNAL = "EXTERNAL"


class Resolution(Enum):
    RESOLVED = "RESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    UNRESOLVED = "UNRESOLVED"
    EXTERNAL = "EXTERNAL"


class Intent(Enum):
    KEEP = "KEEP"
    CREATE = "CREATE"
    CHANGE = "CHANGE"
    REMOVE = "REMOVE"


class DesignLevel(Enum):
    SYSTEM = "SYSTEM"
    PACKAGE = "PACKAGE"
    CODE = "CODE"


class DesignKind(Enum):
    UNKNOWN = "unknown"
    SYSTEM = "system"
    PACKAGE = "package"
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"


class ApplyStatus(Enum):
    APPLIED = "APPLIED"
    CONFLICT = "CONFLICT"
    REJECTED = "REJECTED"
    DUPLICATE = "DUPLICATE"


@dataclass(frozen=True)
class DesignNode:
    id: str
    label: str
    level: str
    provenance: str
    location: str
    intent: str
    parent_id: str | None = None
    locator: str | None = None
    description: str = ""
    kind: str = DesignKind.UNKNOWN.value
    target_path: str = ""
    qualified_name: str = ""
    signature: str = ""
    docstring: str = ""
    satisfies: tuple[str, ...] = ()
    acceptance: tuple[str, ...] = ()

    def to_json(self) -> dict[str, object]:
        return {
            **self.__dict__,
            "satisfies": list(self.satisfies),
            "acceptance": list(self.acceptance),
        }


@dataclass(frozen=True)
class DesignEdge:
    source: str
    target: str
    relation: str
    provenance: str
    intent: str


@dataclass(frozen=True)
class ApplyResult:
    status: ApplyStatus
    revision: int
    detail: str = ""


@dataclass(frozen=True)
class OperationRecord:
    seq: int
    operation_id: str
    author: str
    base_revision: int
    status: ApplyStatus
    detail: str


@dataclass(frozen=True)
class SnapshotResult:
    status: ApplyStatus
    snapshot: dict | None
