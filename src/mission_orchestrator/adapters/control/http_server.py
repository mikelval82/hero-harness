from __future__ import annotations

import json
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from mission_orchestrator.adapters.control.openapi import openapi_document
from mission_orchestrator.application.control_plane import MissionControlPlane
from mission_orchestrator.application.contract_execution import (
    ExecutionConflictError,
    ExecutionValidationError,
)
from mission_orchestrator.application.preparation_coordinator import InvalidSessionAction
from mission_orchestrator.domain.design import ApplyStatus
from mission_orchestrator.domain.document import DocumentSaveStatus
from mission_orchestrator.ports.session_store import SessionConflictError


API_PREFIX = "/api/v1"
MAX_BODY_BYTES = 2 * 1024 * 1024
MAX_EVENT_WAIT_SECONDS = 30.0
EVENT_POLL_SECONDS = 0.25
LOCAL_ORIGINS = {"localhost", "127.0.0.1", "::1"}


class OperationInProgress(RuntimeError):
    def __init__(self, operation_id: str) -> None:
        super().__init__(f"operation {operation_id} is still running")
        self.operation_id = operation_id


@dataclass
class AsyncActionRunner:
    control: MissionControlPlane
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _active_id: str = ""
    _operations: dict[str, dict[str, object]] = field(default_factory=dict)
    _commands: dict[str, str] = field(default_factory=dict)

    def submit(self, action: str, body: dict) -> dict[str, object]:
        command_id = str(body.get("command_id", "")).strip() or uuid.uuid4().hex
        with self._lock:
            previous_id = self._commands.get(command_id)
            if previous_id is not None:
                return dict(self._operations[previous_id])
            if self._active_id:
                active = self._operations.get(self._active_id, {})
                if active.get("status") == "running":
                    raise OperationInProgress(self._active_id)
            operation_id = uuid.uuid4().hex
            operation = {
                "operation_id": operation_id,
                "command_id": command_id,
                "action": action,
                "status": "running",
            }
            self._active_id = operation_id
            self._operations[operation_id] = operation
            self._commands[command_id] = operation_id
        thread = threading.Thread(
            target=self._run,
            args=(operation_id, action, dict(body)),
            name=f"mission-{action}",
            daemon=True,
        )
        thread.start()
        return dict(operation)

    def current(self) -> dict[str, object] | None:
        with self._lock:
            if not self._active_id:
                return None
            return dict(self._operations[self._active_id])

    def _run(self, operation_id: str, action: str, body: dict) -> None:
        self.control.services.events.publish(
            "operation_started",
            {"operation_id": operation_id, "action": action},
        )
        try:
            result = self.control.run_action(action, body)
            update: dict[str, object] = {
                "status": "completed" if result.accepted else "rejected",
                "accepted": result.accepted,
                "detail": result.detail,
                "session": result.session.to_json(),
            }
        except Exception as error:
            update = {
                "status": "failed",
                "accepted": False,
                "error": error.__class__.__name__,
                "detail": str(error),
            }
        with self._lock:
            self._operations[operation_id].update(update)
        self.control.services.events.publish(
            "operation_finished",
            {"operation_id": operation_id, "action": action} | update,
        )


class ControlHttpServer:
    def __init__(
        self,
        control: MissionControlPlane,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        token: str | None = None,
    ) -> None:
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("control server may only bind to a loopback host")
        self.control = control
        self.host = host
        self.port = port
        self.token = token or secrets.token_urlsafe(32)
        self.actions = AsyncActionRunner(control)
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> str:
        self._httpd = ThreadingHTTPServer((self.host, self.port), _handler_for(self))
        self._httpd.daemon_threads = True
        self.port = int(self._httpd.server_address[1])
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="harness-control-http",
            daemon=True,
        )
        self._thread.start()
        return self.base_url

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None

    def events(self, after_id: int, wait_seconds: float) -> dict[str, object]:
        deadline = time.monotonic() + min(max(wait_seconds, 0.0), MAX_EVENT_WAIT_SECONDS)
        while True:
            events = self.control.services.events.events_since(after_id)
            if events or time.monotonic() >= deadline:
                return {
                    "events": [
                        {
                            "event_id": event.event_id,
                            "timestamp": event.timestamp,
                            "mission": event.mission,
                            "kind": event.kind,
                            "task_id": event.task_id,
                            "snapshot_id": event.snapshot_id,
                            "payload": event.payload,
                        }
                        for event in events
                    ]
                }
            time.sleep(EVENT_POLL_SECONDS)


def _handler_for(server: ControlHttpServer) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # noqa: A002
            return None

        def do_OPTIONS(self) -> None:  # noqa: N802
            if not self._origin_allowed():
                self._problem("forbidden_origin", "request origin is not local", HTTPStatus.FORBIDDEN)
                return
            self.send_response(HTTPStatus.NO_CONTENT)
            self._cors_headers()
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == f"{API_PREFIX}/health":
                self._json({"ok": True, "api_version": "v1"})
                return
            if parsed.path == f"{API_PREFIX}/openapi.json":
                self._json(openapi_document())
                return
            if not self._authorize(parsed):
                return
            try:
                if parsed.path == f"{API_PREFIX}/snapshot":
                    self._json(server.control.snapshot())
                elif parsed.path == f"{API_PREFIX}/capabilities":
                    self._json(server.control.capabilities())
                elif parsed.path == f"{API_PREFIX}/design":
                    self._json(server.control.design())
                elif parsed.path == f"{API_PREFIX}/operation":
                    self._json({"operation": server.actions.current()})
                elif parsed.path == f"{API_PREFIX}/events":
                    query = parse_qs(parsed.query)
                    after = _integer_query(query, "after", 0)
                    wait = _float_query(query, "wait", 0.0)
                    self._json(server.events(after, wait))
                elif parsed.path == f"{API_PREFIX}/messages":
                    query = parse_qs(parsed.query)
                    after = _integer_query(query, "after", 0)
                    self._json(server.control.messages(after_sequence=after))
                elif parsed.path.startswith(f"{API_PREFIX}/ask/"):
                    operation_id = unquote(parsed.path.removeprefix(f"{API_PREFIX}/ask/"))
                    self._json(server.control.ask_operation(operation_id))
                elif parsed.path == f"{API_PREFIX}/contracts/tasks":
                    self._json(server.control.contract_tasks())
                elif parsed.path.startswith(f"{API_PREFIX}/contracts/tasks/"):
                    task_id = unquote(parsed.path.removeprefix(f"{API_PREFIX}/contracts/tasks/"))
                    self._json(server.control.contract_task(task_id))
                elif parsed.path.startswith(f"{API_PREFIX}/documents/"):
                    logical_id = _document_id(parsed.path)
                    query = parse_qs(parsed.query)
                    revision = _optional_integer_query(query, "revision")
                    payload = server.control.document(logical_id, revision)
                    if payload is None:
                        self._problem("document_not_found", "document was not found", HTTPStatus.NOT_FOUND)
                    else:
                        self._json(payload)
                else:
                    self._problem("not_found", "resource was not found", HTTPStatus.NOT_FOUND)
            except ValueError as error:
                self._problem("invalid_request", str(error), HTTPStatus.BAD_REQUEST)
            except Exception as error:
                self._internal_error(error)

        def do_PUT(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if not self._authorize(parsed):
                return
            if not parsed.path.startswith(f"{API_PREFIX}/documents/"):
                self._problem("not_found", "resource was not found", HTTPStatus.NOT_FOUND)
                return
            try:
                body = self._body()
                result = server.control.save_document(
                    logical_id=_document_id(parsed.path),
                    content=str(body["content"]),
                    base_revision=_required_integer(body, "base_revision"),
                    command_id=str(body["command_id"]),
                )
                payload = {
                    "status": result.status.value,
                    "revision": result.revision,
                    "current_revision": result.current_revision,
                    "detail": result.detail,
                }
                status = (
                    HTTPStatus.CONFLICT
                    if result.status is DocumentSaveStatus.CONFLICT
                    else HTTPStatus.OK
                )
                self._json(payload, status)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                self._problem("invalid_request", str(error), HTTPStatus.BAD_REQUEST)
            except Exception as error:
                self._internal_error(error)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if not self._authorize(parsed):
                return
            try:
                body = self._body()
                if parsed.path.startswith(f"{API_PREFIX}/actions/"):
                    action = unquote(parsed.path.removeprefix(f"{API_PREFIX}/actions/"))
                    operation = server.actions.submit(action, body)
                    self._json(operation, HTTPStatus.ACCEPTED)
                elif parsed.path == f"{API_PREFIX}/contracts/executions":
                    self._json(
                        server.control.begin_contract_execution(
                            task_id=str(body.get("task_id", "")),
                            actor=str(body.get("actor", "")),
                        ),
                        HTTPStatus.CREATED,
                    )
                elif parsed.path.startswith(f"{API_PREFIX}/contracts/executions/"):
                    execution_id, action = _execution_action(parsed.path)
                    detail = str(body.get("detail", ""))
                    if action == "validate":
                        payload = server.control.validate_contract_execution(execution_id)
                    elif action == "read-file":
                        payload = server.control.read_contract_file(
                            execution_id,
                            str(body.get("path", "")),
                        )
                    elif action == "apply-patch":
                        payload = server.control.apply_contract_patch(
                            execution_id,
                            path=str(body.get("path", "")),
                            expected_sha256=str(body.get("expected_sha256", "")),
                            old_text=str(body.get("old_text", "")),
                            new_text=str(body.get("new_text", "")),
                        )
                    elif action == "checks":
                        payload = server.control.run_contract_checks(execution_id)
                    elif action == "complete":
                        payload = server.control.complete_contract_execution(execution_id)
                    elif action == "blocker":
                        payload = server.control.report_contract_blocker(execution_id, detail)
                    elif action == "amendment":
                        operations = body.get("operations")
                        if operations is not None and not isinstance(operations, list):
                            raise ValueError("operations must be a list")
                        payload = server.control.propose_contract_amendment(
                            execution_id,
                            detail,
                            operations=operations,
                            operation_id=str(body.get("operation_id", "")),
                        )
                    else:
                        raise ValueError(f"unknown contract execution action: {action}")
                    self._json(payload)
                elif parsed.path == f"{API_PREFIX}/design/operations":
                    operations = body.get("operations")
                    if not isinstance(operations, list):
                        raise ValueError("operations must be a list")
                    payload = server.control.apply_design(
                        base_revision=_required_integer(body, "base_revision"),
                        operations=operations,
                        operation_id=str(body.get("operation_id", "")),
                    )
                    status = HTTPStatus.OK
                    if payload["status"] == ApplyStatus.CONFLICT.value:
                        status = HTTPStatus.CONFLICT
                    elif payload["status"] == ApplyStatus.REJECTED.value:
                        status = HTTPStatus.UNPROCESSABLE_ENTITY
                    self._json(payload, status)
                elif parsed.path == f"{API_PREFIX}/code-graph/query":
                    self._json(server.control.code_graph_query(body))
                elif parsed.path == f"{API_PREFIX}/ask":
                    self._json(server.control.ask(str(body.get("question", ""))), HTTPStatus.ACCEPTED)
                elif parsed.path == f"{API_PREFIX}/commands":
                    self._json(server.control.submit_command(str(body["text"])))
                else:
                    self._problem("not_found", "resource was not found", HTTPStatus.NOT_FOUND)
            except OperationInProgress as error:
                self._problem(
                    "operation_in_progress",
                    "another operation is still running",
                    HTTPStatus.CONFLICT,
                    details={"operation_id": error.operation_id},
                )
            except ExecutionConflictError as error:
                self._problem("execution_conflict", str(error), HTTPStatus.CONFLICT)
            except ExecutionValidationError as error:
                self._problem(
                    "contract_validation_failed",
                    str(error),
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                )
            except SessionConflictError as error:
                self._problem(
                    "session_conflict",
                    "session revision is stale",
                    HTTPStatus.CONFLICT,
                    current_revision=error.current_revision,
                )
            except InvalidSessionAction as error:
                self._problem("invalid_session_action", str(error), HTTPStatus.CONFLICT)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                self._problem("invalid_request", str(error), HTTPStatus.BAD_REQUEST)
            except Exception as error:
                self._internal_error(error)

        def _authorize(self, parsed) -> bool:  # noqa: ANN001
            if not self._origin_allowed():
                self._problem("forbidden_origin", "request origin is not local", HTTPStatus.FORBIDDEN)
                return False
            header = self.headers.get("Authorization", "")
            query_token = parse_qs(parsed.query).get("token", [""])[0]
            supplied = header.removeprefix("Bearer ") if header.startswith("Bearer ") else query_token
            if not supplied or not secrets.compare_digest(supplied, server.token):
                self._problem("unauthorized", "bearer token is missing or invalid", HTTPStatus.UNAUTHORIZED)
                return False
            return True

        def _origin_allowed(self) -> bool:
            origin = self.headers.get("Origin")
            return not origin or urlparse(origin).hostname in LOCAL_ORIGINS

        def _body(self) -> dict:
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                raise ValueError("Content-Length is required")
            length = int(raw_length)
            if length < 0 or length > MAX_BODY_BYTES:
                raise ValueError("request body is too large")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("request body must be a JSON object")
            return payload

        def _internal_error(self, error: Exception) -> None:
            server.control.services.events.publish(
                "control_error",
                {"error": error.__class__.__name__, "detail": str(error)},
            )
            self._problem("internal_error", "request could not be completed", HTTPStatus.INTERNAL_SERVER_ERROR)

        def _problem(
            self,
            code: str,
            message: str,
            status: HTTPStatus,
            *,
            details: dict[str, object] | None = None,
            current_revision: int | None = None,
        ) -> None:
            payload: dict[str, object] = {
                "code": code,
                "message": message,
                "details": details or {},
            }
            if current_revision is not None:
                payload["current_revision"] = current_revision
            self._json(payload, status)

        def _json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self._cors_headers()
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionError):
                return

        def _cors_headers(self) -> None:
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).hostname in LOCAL_ORIGINS:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")

    return Handler


def _document_id(path: str) -> str:
    encoded = path.removeprefix(f"{API_PREFIX}/documents/")
    logical_id = unquote(encoded).strip("/")
    if not logical_id:
        raise ValueError("logical document id is required")
    return logical_id


def _execution_action(path: str) -> tuple[str, str]:
    suffix = path.removeprefix(f"{API_PREFIX}/contracts/executions/")
    parts = suffix.split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError("contract execution path must contain an execution id and action")
    return unquote(parts[0]), unquote(parts[1])


def _required_integer(body: dict, key: str) -> int:
    value = body.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{key} must be an integer")
    return value


def _integer_query(query: dict[str, list[str]], key: str, default: int) -> int:
    try:
        return int(query.get(key, [str(default)])[0])
    except (TypeError, ValueError):
        return default


def _optional_integer_query(query: dict[str, list[str]], key: str) -> int | None:
    if key not in query:
        return None
    return _integer_query(query, key, 0)


def _float_query(query: dict[str, list[str]], key: str, default: float) -> float:
    try:
        return float(query.get(key, [str(default)])[0])
    except (TypeError, ValueError):
        return default
