from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from mission_orchestrator.adapters.command_bus import QueueCommandBus
from mission_orchestrator.adapters.filesystem.mission_registry import MissionRegistry
from mission_orchestrator.adapters.telegram.listener import ListenerStatus, TelegramListener
from mission_orchestrator.adapters.telegram.lock import TelegramLock, TelegramOffsetStore


class _Artifacts:
    def read_text(self, name, *, default=None):  # noqa: ANN001
        return default or ""


class _State:
    def load_snapshot(self):  # noqa: ANN201
        return None


class TelegramLockAndListenerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bus = QueueCommandBus()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _listener(self) -> TelegramListener:
        return TelegramListener(
            token="test-token",
            chat_id="42",
            mission_tag="project:feature-safe",
            artifacts=_Artifacts(),
            state=_State(),
            commands=self.bus,
            registry=MissionRegistry(self.root / "missions.json"),
            storage_root=self.root,
        )

    def test_token_lock_is_exclusive_and_releasable(self) -> None:
        first = TelegramLock("test-token", self.root)
        second = TelegramLock("test-token", self.root)
        self.assertTrue(first.acquire())
        self.assertFalse(second.acquire())
        first.release()
        self.assertTrue(second.acquire())
        second.release()

    def test_offset_store_synchronizes_backlog_and_persists_next_update(self) -> None:
        store = TelegramOffsetStore("test-token", self.root)
        offset = store.synchronize_backlog(lambda requested: [{"update_id": 8}] if requested == -1 else [])
        self.assertEqual(offset, 9)
        self.assertEqual(store.read(), 9)
        store.write(12)
        self.assertEqual(store.read(), 12)

    def test_control_requires_exact_mission_target(self) -> None:
        listener = self._listener()
        with patch("mission_orchestrator.adapters.telegram.listener.send_message") as send:
            listener._handle("/abort")
            self.assertIsNone(self.bus.get_nowait())
            listener._handle("/abort @project:other")
            self.assertIsNone(self.bus.get_nowait())
            listener._handle("/abort @project:feature-safe")
        command = self.bus.get_nowait()
        self.assertIsNotNone(command)
        self.assertEqual(command.kind.value, "abort")
        self.assertGreaterEqual(send.call_count, 1)

    def test_listener_stop_releases_lock_and_marks_stopped(self) -> None:
        listener = self._listener()
        calls = 0

        def updates(token, offset, timeout=60):  # noqa: ANN001
            nonlocal calls
            calls += 1
            if calls == 1:
                return []
            threading.Event().wait(0.02)
            return []

        with patch("mission_orchestrator.adapters.telegram.listener.get_updates", side_effect=updates):
            handle = listener.start()
            self.assertTrue(handle.stop(timeout=1.0))
        self.assertEqual(handle.health.status, ListenerStatus.STOPPED)
        replacement = TelegramLock("test-token", self.root)
        self.assertTrue(replacement.acquire())
        replacement.release()

    def test_unauthorized_chat_is_not_dispatched_but_offset_can_advance(self) -> None:
        listener = self._listener()
        listener._handle_update(
            {"message": {"chat": {"id": 7, "type": "private"}, "from": {"id": 7}, "text": "/abort @project:feature-safe"}}
        )
        self.assertIsNone(self.bus.get_nowait())


if __name__ == "__main__":
    unittest.main()
