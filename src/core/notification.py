from __future__ import annotations

from typing import Optional, Callable


_notify_backend: Optional[Callable] = None
_notify_prefix = ""


def set_notify_backend(fn: Callable) -> None:
    global _notify_backend
    _notify_backend = fn


def set_notify_prefix(prefix: str) -> None:
    global _notify_prefix
    _notify_prefix = prefix


def notify(msg: str) -> None:
    if _notify_backend is not None:
        _notify_backend(msg, prefix=_notify_prefix)
