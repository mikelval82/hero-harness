"""Mission registry I/O — atomic read/write of ~/.harness/_missions.json."""
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

REGISTRY_PATH = Path.home() / ".harness" / "_missions.json"


def _read_registry() -> dict:
    try:
        return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_registry(data: dict) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd = tempfile.NamedTemporaryFile(
        mode="w", dir=REGISTRY_PATH.parent, suffix=".tmp",
        delete=False, encoding="utf-8",
    )
    try:
        fd.write(json.dumps(data, indent=2))
        fd.close()
        os.replace(fd.name, REGISTRY_PATH)
    except BaseException:
        fd.close()
        try:
            os.unlink(fd.name)
        except OSError:
            pass
        raise


def register_mission(tag: str, harness_path: str, pid: int) -> None:
    if not tag:
        raise ValueError("tag must be non-empty")
    if not harness_path:
        raise ValueError("harness_path must be non-empty")
    data = _read_registry()
    data[tag] = {
        "harness_path": harness_path,
        "pid": pid,
        "started": datetime.now().isoformat(timespec="seconds"),
    }
    _write_registry(data)


def unregister_mission(tag: str) -> None:
    data = _read_registry()
    if tag in data:
        del data[tag]
        _write_registry(data)


def list_missions() -> dict:
    return _read_registry()
