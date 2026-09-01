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


def _node_op(node_id: str, label: str) -> dict:
    return {
        "op": "add_node",
        "id": node_id,
        "label": label,
        "level": "CODE",
        "provenance": "HUMAN",
        "location": "IN_REPOSITORY",
        "intent": "CREATE",
    }


class DesignProposeEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.harness = Path(self._tmp.name)
        _seed(DesignStore(self.harness / "design.db"))  # revision 1: svc, cache
        self.server = MissionWebServer(self.harness, mission="PROJ:feature-x")
        self.server.start()

    def tearDown(self) -> None:
        self.server.stop()
        self._tmp.cleanup()

    def _request(self, path: str, body: object | bytes, *, token: bool = True, origin: str | None = None):
        data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.server.port}{path}", data=data, method="POST"
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

    def _propose(self, body: object | bytes, **kwargs):
        return self._request("/api/design/propose", body, **kwargs)

    def _map(self) -> dict:
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.server.port}/api/map?token={self.server.token}"
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_g1_valid_operation_applies_with_human_author(self) -> None:
        status, payload = self._propose(
            {"operation_id": "human-1", "base_revision": 1, "operations": [_node_op("queue", "Job queue")]}
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "APPLIED")
        self.assertEqual(payload["design_revision"], 2)

        map_state = self._map()
        self.assertIn("queue", {node["id"] for node in map_state["nodes"]})

        history = DesignStore(self.harness / "design.db").history()
        self.assertEqual(history[-1].operation_id, "human-1")
        self.assertEqual(history[-1].author, "HUMAN")

    def test_g2_stale_base_revision_conflicts(self) -> None:
        status, payload = self._propose(
            {"operation_id": "human-2", "base_revision": 0, "operations": [_node_op("queue", "Q")]}
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "CONFLICT")
        self.assertNotIn("queue", {node["id"] for node in self._map()["nodes"]})

    def test_g3_invalid_operation_is_rejected(self) -> None:
        status, payload = self._propose(
            {"operation_id": "human-3", "base_revision": 1, "operations": [{"op": "add_node", "id": "broken"}]}
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "REJECTED")
        self.assertEqual(self._map()["design_revision"], 1)
        self.assertTrue(payload["detail"])

    def test_g4_duplicate_operation_id(self) -> None:
        body = {"operation_id": "human-4", "base_revision": 1, "operations": [_node_op("queue", "Q")]}
        self._propose(body)
        status, payload = self._propose(body)
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "DUPLICATE")

    def test_g5_auth_and_origin_enforced(self) -> None:
        body = {"base_revision": 1, "operations": [_node_op("queue", "Q")]}
        self.assertEqual(self._propose(body, token=False)[0], 401)
        self.assertEqual(self._propose(body, origin="https://evil.example")[0], 403)
        self.assertNotIn("queue", {node["id"] for node in self._map()["nodes"]})

    def test_g6_applied_proposal_publishes_event(self) -> None:
        self._propose(
            {"operation_id": "human-6", "base_revision": 1, "operations": [_node_op("queue", "Q")]}
        )
        events = SqliteEventLog(self.harness, mission="PROJ:feature-x").events_since(0)
        proposals = [e for e in events if e.kind == "design_proposal"]
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0].payload["author"], "HUMAN")
        self.assertEqual(proposals[0].payload["status"], "APPLIED")
        self.assertEqual(proposals[0].payload["operation_id"], "human-6")

    def test_g7_malformed_body_rejected(self) -> None:
        self.assertEqual(self._propose(b"not json")[0], 400)
        self.assertEqual(self._propose({"operations": [_node_op("q", "Q")]})[0], 400)  # missing base_revision
        self.assertEqual(self._propose({"base_revision": 1, "operations": "nope"})[0], 400)
        self.assertEqual(self._map()["design_revision"], 1)

    def test_g1b_operation_id_generated_when_missing(self) -> None:
        status, payload = self._propose(
            {"base_revision": 1, "operations": [_node_op("queue", "Q")]}
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "APPLIED")
        history = DesignStore(self.harness / "design.db").history()
        self.assertTrue(history[-1].operation_id.startswith("human-"))


if __name__ == "__main__":
    unittest.main()
