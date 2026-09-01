from __future__ import annotations

from typing import Protocol


class MissionLogger(Protocol):
    def log(self, message: str) -> None: ...
    def tool_call(self, name: str, input: dict) -> None: ...
    def metric(self, record: dict) -> None: ...

