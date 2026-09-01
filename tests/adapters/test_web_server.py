from __future__ import annotations

import json
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from mission_orchestrator.adapters.design.store import DesignStore
from mission_orchestrator.adapters.events.sqlite_log import SqliteEventLog
from mission_orchestrator.adapters.web.server import MissionWebServer

from tests.application.test_approval import _seed


class WebServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.harness = Path(self._tmp.name)
        _seed(DesignStore(self.harness / "design.db"))
        self.server = MissionWebServer(self.harness, mission="PROJ:feature-x")
        self.base_url = self.server.start()

    def tearDown(self) -> None:
        self.server.stop()
        self._tmp.cleanup()

    def _get(self, path: str, *, token: str | None = "valid", origin: str | None = None):
        request = urllib.request.Request(f"http://127.0.0.1:{self.server.port}{path}")
        if token == "valid":
            request.add_header("Authorization", f"Bearer {self.server.token}")
        elif token is not None:
            request.add_header("Authorization", f"Bearer {token}")
        if origin is not None:
            request.add_header("Origin", origin)
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def _status_of(self, path: str, **kwargs) -> int:
        try:
            status, _ = self._get(path, **kwargs)
            return status
        except urllib.error.HTTPError as exc:
            return exc.code

    def test_w1_token_required(self) -> None:
        self.assertEqual(self._status_of("/api/map", token=None), 401)
        self.assertEqual(self._status_of("/api/map", token="wrong"), 401)
        self.assertEqual(self._status_of("/api/map"), 200)

    def test_w1_token_accepted_as_query_param(self) -> None:
        status = self._status_of(f"/api/map?token={self.server.token}", token=None)
        self.assertEqual(status, 200)

    def test_w2_foreign_origin_rejected(self) -> None:
        self.assertEqual(self._status_of("/api/map", origin="https://evil.example"), 403)
        self.assertEqual(
            self._status_of("/api/map", origin=f"http://127.0.0.1:{self.server.port}"), 200
        )

    def test_w3_map_exposes_design_store(self) -> None:
        _, payload = self._get("/api/map")
        self.assertEqual(payload["design_revision"], 1)
        self.assertEqual({node["id"] for node in payload["nodes"]}, {"svc", "cache"})
        self.assertEqual(payload["edges"][0]["relation"], "uses")

    def test_w4_diff_renders_map_diff(self) -> None:
        _, payload = self._get("/api/diff")
        self.assertIn("+ CREATE Cache", payload["text"])
        self.assertEqual(payload["design_revision"], 1)

    def test_w5_snapshot_null_then_content(self) -> None:
        _, payload = self._get("/api/snapshot")
        self.assertIsNone(payload)

        (self.harness / "approved_snapshot.json").write_text(
            json.dumps({"snapshot_id": "abc123", "design_revision": 1}), encoding="utf-8"
        )
        _, payload = self._get("/api/snapshot")
        self.assertEqual(payload["snapshot_id"], "abc123")

    def test_w6_events_since(self) -> None:
        log = SqliteEventLog(self.harness, mission="PROJ:feature-x")
        log.publish("phase_started", {"phase": "research", "mode": "focused"})
        log.publish("tool_call", {"tool": "Read", "summary": "Reading x"})

        _, payload = self._get("/api/events?after=1")
        self.assertEqual(len(payload["events"]), 1)
        event = payload["events"][0]
        self.assertEqual(event["event_id"], 2)
        self.assertEqual(event["kind"], "tool_call")
        self.assertEqual(event["payload"]["tool"], "Read")

    def test_w7_unknown_route_and_history(self) -> None:
        self.assertEqual(self._status_of("/api/nope"), 404)
        _, history = self._get("/api/history")
        self.assertEqual(history[0]["operation_id"], "seed")
        self.assertEqual(history[0]["status"], "APPLIED")


if __name__ == "__main__":
    unittest.main()
