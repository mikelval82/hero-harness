"""Single-bot process lock and durable Telegram update offset."""

from __future__ import annotations

import errno
import hashlib
import os
import tempfile
import threading
from pathlib import Path
from typing import Callable, Mapping, Sequence


def token_hash(token: str) -> str:
    """Return a stable, non-reversible identifier safe for filenames."""

    if not token:
        raise ValueError("Telegram token is required")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _root_path(root: str | Path | None) -> Path:
    return Path(root) if root is not None else Path.home() / ".harness"


class TelegramLock:
    """Non-blocking, cross-platform lock implementing one mission per bot.

    The lock is held by the open descriptor.  Its file is intentionally never
    deleted: deleting a locked inode would allow a second process to lock a new
    file at the same path.
    """

    def __init__(self, token: str, root: str | Path | None = None) -> None:
        self.token_id = token_hash(token)
        self.root = _root_path(root)
        self.path = self.root / f"_telegram_{self.token_id}.lock"
        self._file = None
        self._guard = threading.Lock()

    @property
    def acquired(self) -> bool:
        return self._file is not None

    def acquire(self) -> bool:
        """Acquire without waiting; return False when another owner exists."""

        with self._guard:
            if self._file is not None:
                return True
            self.root.mkdir(parents=True, exist_ok=True)
            handle = self.path.open("a+b")
            try:
                self._ensure_lock_byte(handle)
                self._lock_descriptor(handle)
            except OSError as exc:
                handle.close()
                if self._is_contention(exc):
                    return False
                raise
            self._file = handle
            return True

    def release(self) -> None:
        """Release and close idempotently, retaining the lock file."""

        with self._guard:
            handle = self._file
            if handle is None:
                return
            self._file = None
            try:
                self._unlock_descriptor(handle)
            finally:
                handle.close()

    def __enter__(self) -> "TelegramLock":
        if not self.acquire():
            raise RuntimeError("Telegram bot is already controlled by another mission")
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.release()

    @staticmethod
    def _ensure_lock_byte(handle) -> None:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
            os.fsync(handle.fileno())
        handle.seek(0)

    @staticmethod
    def _lock_descriptor(handle) -> None:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    @staticmethod
    def _unlock_descriptor(handle) -> None:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _is_contention(exc: OSError) -> bool:
        if os.name == "nt":
            return exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}
        return exc.errno in {errno.EACCES, errno.EAGAIN}


class TelegramOffsetStore:
    """Atomic, global update offset for one Telegram token."""

    def __init__(self, token: str, root: str | Path | None = None) -> None:
        self.token_id = token_hash(token)
        self.root = _root_path(root)
        self.path = self.root / f"_telegram_{self.token_id}.offset"

    def read(self) -> int | None:
        """Return None for missing/corrupt state so startup can fail safe."""

        try:
            raw = self.path.read_text(encoding="ascii").strip()
            value = int(raw)
        except (FileNotFoundError, OSError, UnicodeError, ValueError):
            return None
        return value if value >= 0 else None

    def write(self, next_offset: int) -> None:
        if isinstance(next_offset, bool) or not isinstance(next_offset, int):
            raise TypeError("Telegram offset must be an integer")
        if next_offset < 0:
            raise ValueError("Telegram offset must be non-negative")

        self.root.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=self.root,
        )
        try:
            with os.fdopen(fd, "w", encoding="ascii", newline="\n") as handle:
                handle.write(f"{next_offset}\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.path)
            self._sync_directory()
        except BaseException:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
            raise

    def synchronize_backlog(
        self,
        fetch_updates: Callable[[int], Sequence[Mapping[str, object]]],
    ) -> int:
        """Discard startup backlog and persist the first future offset.

        ``fetch_updates`` must perform ``getUpdates`` for the supplied offset.
        Telegram's ``offset=-1`` returns the newest pending update and forgets
        earlier ones.  Persisting its successor gives a new mission at-most-once
        startup semantics.
        """

        updates = fetch_updates(-1)
        update_ids = [
            value
            for update in updates
            if isinstance(update, Mapping)
            and isinstance((value := update.get("update_id")), int)
            and not isinstance(value, bool)
            and value >= 0
        ]
        # Do not compare this with a persisted historical offset. Telegram may
        # choose a random update_id after a week without updates, so the old
        # numeric range is not a safe lower bound for the new session.
        next_offset = max(update_ids) + 1 if update_ids else 0
        self.write(next_offset)
        return next_offset

    def load_or_synchronize(
        self,
        fetch_updates: Callable[[int], Sequence[Mapping[str, object]]],
    ) -> int:
        """Prepare one listener startup without replaying downtime commands.

        Synchronization runs at every process start, not only when the offset
        file is absent. Otherwise a command sent after mission A stopped could
        remain in Telegram's backlog and unexpectedly control mission B.
        """

        return self.synchronize_backlog(fetch_updates)

    def _sync_directory(self) -> None:
        if os.name == "nt":
            return
        descriptor = os.open(self.root, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
