from __future__ import annotations

import os
from pathlib import Path


class FilesystemArtifactStore:
    def __init__(self, harness_dir: Path) -> None:
        self.harness_dir = harness_dir.resolve()
        self.harness_dir.mkdir(parents=True, exist_ok=True)

    def exists(self, name: str) -> bool:
        return self.path_for(name).exists()

    def read_text(self, name: str, *, default: str | None = None) -> str:
        path = self.path_for(name)
        if not path.exists():
            if default is not None:
                return default
            raise FileNotFoundError(path)
        return path.read_text(encoding="utf-8")

    def write_text(self, name: str, content: str) -> None:
        path = self.path_for(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)

    def append_text(self, name: str, content: str) -> None:
        path = self.path_for(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(content)

    def delete(self, name: str) -> None:
        path = self.path_for(name)
        if path.exists():
            path.unlink()

    def path_for(self, name: str) -> Path:
        candidate = Path(name)
        if candidate.is_absolute():
            raise ValueError(f"Artifact path must be relative: {name}")
        resolved = (self.harness_dir / candidate).resolve()
        if resolved != self.harness_dir and self.harness_dir not in resolved.parents:
            raise ValueError(f"Artifact path escapes harness: {name}")
        return resolved

