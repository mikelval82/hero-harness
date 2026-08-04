from __future__ import annotations

import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from mission_orchestrator.adapters.design.store import DesignStore
from mission_orchestrator.adapters.events.sqlite_log import SqliteEventLog
from mission_orchestrator.domain.command import parse_control_command
from mission_orchestrator.domain.map_diff import render_map_diff
from mission_orchestrator.ports.command_bus import CommandBus

_LOCAL_HOSTS = {"127.0.0.1", "localhost"}
_MAX_WAIT_SECONDS = 30.0
_POLL_INTERVAL_SECONDS = 0.4
_STATIC_DIR = Path(__file__).parent / "static"

_PLACEHOLDER_HTML = "<!doctype html><title>HERO</title><p>HERO mission server online.</p>"


class MissionWebServer:
    def __init__(
        self,
        harness_dir: Path,
        mission: str,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        commands: CommandBus | None = None,
    ) -> None:
        self.harness_dir = harness_dir
        self.mission = mission
        self.host = host
        self.port = port
        self.commands = commands
        self.token = secrets.token_urlsafe(16)
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> str:
        handler = _build_handler(self)
        self._httpd = ThreadingHTTPServer((self.host, self.port), handler)
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return f"http://{self.host}:{self.port}/?token={self.token}"

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None

    # --- contract reads (fresh adapters per call: served from worker threads) ---

    def map_payload(self) -> dict:
        store = DesignStore(self.harness_dir / "design.db")
        return {
            "design_revision": store.current_revision(),
            "nodes": [node.__dict__ for node in store.nodes()],
            "edges": [edge.__dict__ for edge in store.edges()],
        }

    def diff_payload(self) -> dict:
        store = DesignStore(self.harness_dir / "design.db")
        return {
            "design_revision": store.current_revision(),
            "text": render_map_diff(store.nodes(), store.edges()),
        }

    def snapshot_payload(self) -> dict | None:
        path = self.harness_dir / "approved_snapshot.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def history_payload(self) -> list[dict]:
        store = DesignStore(self.harness_dir / "design.db")
        return [
            {
                "seq": record.seq,
                "operation_id": record.operation_id,
                "author": record.author,
                "base_revision": record.base_revision,
                "status": record.status.value,
                "detail": record.detail,
            }
            for record in store.history()
        ]

    def events_payload(self, after_id: int, wait_seconds: float) -> dict:
        log = SqliteEventLog(self.harness_dir, mission=self.mission)
        deadline = time.monotonic() + min(max(wait_seconds, 0.0), _MAX_WAIT_SECONDS)
        while True:
            events = log.events_since(after_id)
            if events or time.monotonic() >= deadline:
                return {"events": [event.__dict__ for event in events]}
            time.sleep(_POLL_INTERVAL_SECONDS)


def _build_handler(server: MissionWebServer) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # noqa: A002
            return None

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            if not self._origin_allowed():
                self._send_json({"error": "forbidden origin"}, status=403)
                return
            if not self._authorized(query):
                self._send_json({"error": "unauthorized"}, status=401)
                return

            route = parsed.path
            if route == "/":
                self._send_html(_index_html())
            elif route == "/api/map":
                self._send_json(server.map_payload())
            elif route == "/api/diff":
                self._send_json(server.diff_payload())
            elif route == "/api/snapshot":
                self._send_json(server.snapshot_payload())
            elif route == "/api/history":
                self._send_json(server.history_payload())
            elif route == "/api/events":
                after = _int_param(query, "after", 0)
                wait = _float_param(query, "wait", 0.0)
                self._send_json(server.events_payload(after, wait))
            else:
                self._send_json({"error": "not found"}, status=404)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            if not self._origin_allowed():
                self._send_json({"error": "forbidden origin"}, status=403)
                return
            if not self._authorized(query):
                self._send_json({"error": "unauthorized"}, status=401)
                return
            if parsed.path != "/api/command":
                self._send_json({"error": "not found"}, status=404)
                return
            if server.commands is None:
                self._send_json({"error": "command bus unavailable"}, status=503)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                text = str(body["text"])
            except Exception:
                self._send_json({"error": "invalid body"}, status=400)
                return
            command = parse_control_command(text)
            if command is None:
                self._send_json({"error": "empty command"}, status=400)
                return
            server.commands.publish(command)
            self._send_json({"accepted": True, "kind": command.kind.value})

        def _authorized(self, query: dict[str, list[str]]) -> bool:
            header = self.headers.get("Authorization", "")
            if header == f"Bearer {server.token}":
                return True
            return query.get("token", [None])[0] == server.token

        def _origin_allowed(self) -> bool:
            origin = self.headers.get("Origin")
            if not origin:
                return True
            host = urlparse(origin).hostname
            return host in _LOCAL_HOSTS

        def _send_json(self, payload: object, *, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send_bytes(body, "application/json; charset=utf-8", status)

        def _send_html(self, html: str) -> None:
            self._send_bytes(html.encode("utf-8"), "text/html; charset=utf-8", 200)

        def _send_bytes(self, body: bytes, content_type: str, status: int) -> None:
            try:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (ConnectionError, BrokenPipeError):
                pass  # client went away (e.g. reload during long-poll)

    return Handler


def _int_param(query: dict[str, list[str]], key: str, default: int) -> int:
    try:
        return int(query.get(key, [default])[0])
    except (TypeError, ValueError):
        return default


def _index_html() -> str:
    path = _STATIC_DIR / "index.html"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return _PLACEHOLDER_HTML


def _float_param(query: dict[str, list[str]], key: str, default: float) -> float:
    try:
        return float(query.get(key, [default])[0])
    except (TypeError, ValueError):
        return default
