from __future__ import annotations

import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from mission_orchestrator.adapters.web.server import MissionWebServer


class CasConflictUiTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.server = MissionWebServer(Path(self._tmp.name), mission="PROJ:feature-x")
        self.server.start()

    def tearDown(self) -> None:
        self.server.stop()
        self._tmp.cleanup()

    def test_j1_conflict_flow_wired(self) -> None:
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.server.port}/?token={self.server.token}"
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            html = response.read().decode("utf-8")
        self.assertIn("map reloaded at revision", html)
        self.assertIn("no longer exists", html)
        # background refresh rebinds the inspected node to the fresh instance
        self.assertIn("rebindInspector", html)


if __name__ == "__main__":
    unittest.main()
