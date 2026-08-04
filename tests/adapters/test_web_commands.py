from __future__ import annotations

import json
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from mission_orchestrator.adapters.command_bus import QueueCommandBus
from mission_orchestrator.adapters.web.server import MissionWebServer
from mission_orchestrator.domain.command import CommandKind


class WebCommandsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.commands = QueueCommandBus()
        self.server = MissionWebServer(
            Path(self._tmp.name), mission="PROJ:feature-x", commands=self.commands
        )
        self.server.start()

    def tearDown(self) -> None:
        self.server.stop()
        self._tmp.cleanup()

    def _post(self, body: object, *, token: bool = True, origin: str | None = None):
        data = json.dumps(body).encode("utf-8") if not isinstance(body, bytes) else body
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.server.port}/api/command", data=data, method="POST"
        )
        request.add_header("Content-Type", "application/json")
        if token:
            request.add_header("Authorization", f"Bearer {self.server.token}")
        if origin is not None:
            request.add_header("Origin", origin)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, None

    def test_c1_approve_reaches_command_bus(self) -> None:
        status, payload = self._post({"text": "/approve"})
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"accepted": True, "kind": "approve"})
        command = self.commands.get_nowait()
        self.assertEqual(command.kind, CommandKind.APPROVE)

    def test_c2_reject_keeps_reason(self) -> None:
        status, _ = self._post({"text": "/reject too big"})
        self.assertEqual(status, 200)
        command = self.commands.get_nowait()
        self.assertEqual(command.kind, CommandKind.REJECT)
        self.assertEqual(command.reason, "too big")

    def test_c3_auth_and_origin_enforced(self) -> None:
        self.assertEqual(self._post({"text": "/approve"}, token=False)[0], 401)
        self.assertEqual(
            self._post({"text": "/approve"}, origin="https://evil.example")[0], 403
        )
        self.assertIsNone(self.commands.get_nowait())

    def test_c4_invalid_body_rejected(self) -> None:
        self.assertEqual(self._post({"text": "   "})[0], 400)
        self.assertEqual(self._post(b"not json")[0], 400)
        self.assertEqual(self._post({"nope": 1})[0], 400)
        self.assertIsNone(self.commands.get_nowait())

    def test_c5_plain_text_is_answer(self) -> None:
        status, payload = self._post({"text": "use the simpler layout"})
        self.assertEqual(status, 200)
        self.assertEqual(payload["kind"], "answer")
        command = self.commands.get_nowait()
        self.assertEqual(command.kind, CommandKind.ANSWER)
        self.assertEqual(command.text, "use the simpler layout")

    def test_c6_read_only_server_returns_503(self) -> None:
        readonly = MissionWebServer(Path(self._tmp.name), mission="PROJ:feature-x")
        readonly.start()
        try:
            request = urllib.request.Request(
                f"http://127.0.0.1:{readonly.port}/api/command",
                data=json.dumps({"text": "/approve"}).encode("utf-8"),
                method="POST",
            )
            request.add_header("Authorization", f"Bearer {readonly.token}")
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(request, timeout=5)
            self.assertEqual(ctx.exception.code, 503)
        finally:
            readonly.stop()


if __name__ == "__main__":
    unittest.main()
