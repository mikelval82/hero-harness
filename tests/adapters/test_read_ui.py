from __future__ import annotations

import re
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from mission_orchestrator.adapters.web import server as web_server
from mission_orchestrator.adapters.web.server import MissionWebServer


class ReadUiTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.server = MissionWebServer(Path(self._tmp.name), mission="PROJ:feature-x")
        self.server.start()

    def tearDown(self) -> None:
        self.server.stop()
        self._tmp.cleanup()

    def _get_root(self) -> tuple[str, str]:
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.server.port}/?token={self.server.token}"
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.headers.get("Content-Type", ""), response.read().decode("utf-8")

    def test_u1_root_serves_application(self) -> None:
        content_type, html = self._get_root()
        self.assertIn("text/html", content_type)
        self.assertIn("<svg", html)
        self.assertIn('id="diff-text"', html)
        self.assertIn('id="approve"', html)
        self.assertIn('id="reject"', html)
        self.assertIn('id="events"', html)
        self.assertIn('id="history"', html)

    def test_u2_no_external_resources(self) -> None:
        _, html = self._get_root()
        external = re.findall(r"https?://(?!127\.0\.0\.1|localhost)[^\s\"']+", html)
        # XML namespace identifiers are not fetched resources.
        external = [url for url in external if not url.startswith("http://www.w3.org/")]
        self.assertEqual(external, [])
        self.assertNotIn("<script src", html)
        self.assertNotIn('<link rel="stylesheet" href="http', html)

    def test_u3_js_uses_public_contracts_only(self) -> None:
        _, html = self._get_root()
        for endpoint in ("/api/map", "/api/diff", "/api/snapshot", "/api/history", "/api/events", "/api/command"):
            self.assertIn(endpoint, html)
        self.assertNotIn(".db", html)

    def test_u4_placeholder_fallback_without_static(self) -> None:
        original = web_server._STATIC_DIR
        web_server._STATIC_DIR = Path(self._tmp.name) / "missing"
        try:
            _, html = self._get_root()
            self.assertIn("HERO mission server online", html)
        finally:
            web_server._STATIC_DIR = original


if __name__ == "__main__":
    unittest.main()
