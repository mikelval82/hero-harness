from __future__ import annotations

import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from mission_orchestrator.adapters.web.server import MissionWebServer


class CreationGesturesTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.server = MissionWebServer(Path(self._tmp.name), mission="PROJ:feature-x")
        self.server.start()

    def tearDown(self) -> None:
        self.server.stop()
        self._tmp.cleanup()

    def _html(self) -> str:
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.server.port}/?token={self.server.token}"
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.read().decode("utf-8")

    def test_h1_multimode_inspector_and_operations(self) -> None:
        html = self._html()
        self.assertIn('id="insp-id"', html)
        self.assertIn('id="insp-relation"', html)
        self.assertIn('id="insp-delete"', html)
        for operation in ("add_node", "add_edge", "remove_node", "remove_edge", "update_node"):
            self.assertIn(operation, html)

    def test_h2_gestures_wired(self) -> None:
        html = self._html()
        self.assertIn("dblclick", html)
        self.assertIn("laneFromY", html)
        self.assertIn("edgeDrag", html)
        # All three lanes always rendered so empty lanes accept double-click.
        self.assertIn("const lanes = LANES", html)


if __name__ == "__main__":
    unittest.main()
