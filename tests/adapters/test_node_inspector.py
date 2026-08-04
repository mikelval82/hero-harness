from __future__ import annotations

import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from mission_orchestrator.adapters.web.server import MissionWebServer


class NodeInspectorTest(unittest.TestCase):
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

    def test_i1_inspector_panel_present(self) -> None:
        html = self._html()
        self.assertIn('id="inspector"', html)
        self.assertIn('id="insp-label"', html)
        self.assertIn('id="insp-intent"', html)
        self.assertIn('id="insp-locator"', html)
        self.assertIn('id="insp-description"', html)
        self.assertIn('id="insp-save"', html)
        self.assertIn('id="insp-close"', html)
        for intent in ("KEEP", "CREATE", "CHANGE", "REMOVE"):
            self.assertIn(f'<option value="{intent}"', html)

    def test_i2_js_sends_only_changed_fields_via_design_propose(self) -> None:
        html = self._html()
        self.assertIn("update_node", html)
        self.assertIn("/api/design/propose", html)
        self.assertIn("changedFields", html)
        self.assertIn("base_revision", html)


if __name__ == "__main__":
    unittest.main()
