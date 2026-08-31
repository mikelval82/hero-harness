from __future__ import annotations

import errno
import hashlib
import os
import tempfile
import threading
from pathlib import Path
from typing import Callable, Mapping, Sequence


def _root(root: Path | None = None) -> Path:
    return root or (Path.home() / ".harness")


def token_id(token: str) -> str:
    if not token:
        raise ValueError("Telegram token is required")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class TelegramLock:
    """Non-blocking, cross-process ownership lock for one Telegram token."""

    def __init__(self, token: str, root: Path | None = None) -> None:
        self.root = _root(root)
        self.path = self.root / f"_telegram_{token_id(token)}.lock"
        self._handle = None
        self._guard = threading.Lock()

    def acquire(self) -> bool:
        with self._guard:
            if self._handle is not None:
                return True
            self.root.mkdir(parents=True, exist_ok=True)
            handle = self.path.open("a+b")
            try:
                if handle.seek(0, os.SEEK_END) == 0:
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                handle.close()
                if exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                    return False
                raise
            self._handle = handle
            return True

    def release(self) -> None:
        with self._guard:
            handle, self._handle = self._handle, None
            if handle is None:
                return
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()


class TelegramOffsetStore:
    """Atomically persist the next offset, scoped by non-reversible token id."""

    def __init__(self, token: str, root: Path | None = None) -> None:
        self.root = _root(root)
        self.path = self.root / f"_telegram_{token_id(token)}.offset"

    def read(self) -> int | None:
        try:
            value = int(self.path.read_text(encoding="ascii").strip())
        except (FileNotFoundError, OSError, UnicodeError, ValueError):
            return None
        return value if value >= 0 else None

    def write(self, value: int) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("Telegram offset must be a non-negative integer")
        self.root.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="ascii", newline="\n") as handle:
                handle.write(f"{value}\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except BaseException:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise

    def synchronize_backlog(self, fetch: Callable[[int], Sequence[Mapping[str, object]]]) -> int:
        updates = fetch(-1)
        ids = [
            value for update in updates if isinstance(update, Mapping)
            and isinstance((value := update.get("update_id")), int) and not isinstance(value, bool)
        ]
        next_offset = max(ids) + 1 if ids else 0
        self.write(next_offset)
        return next_offset
