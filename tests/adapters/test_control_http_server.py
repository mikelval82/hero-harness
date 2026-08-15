from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from mission_orchestrator.adapters.control.http_server import ControlHttpServer
from mission_orchestrator.adapters.documents.sqlite_catalog import SqliteDocumentCatalog
from mission_orchestrator.adapters.filesystem.artifact_store import FilesystemArtifactStore
from mission_orchestrator.adapters.filesystem.session_store import FilesystemMissionSessionStore
from mission_orchestrator.application.control_plane import MissionControlPlane
from mission_orchestrator.application.document_service import MissionDocumentService
from mission_orchestrator.application.interactive_task_coordinator import InteractiveTaskCoordinator
from mission_orchestrator.application.preparation_coordinator import PreparationCoordinator
from mission_orchestrator.domain.mission import MissionMode
from tests.application.test_orchestrator import FakeAgent, make_services


class ControlHttpServerTest(unittest.TestCase):
    def test_authenticated_snapshot_and_document_write(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as raw:
            root = Path(raw)
            agent = FakeAgent(FilesystemArtifactStore(root / "initial"))
            services, context, _ = make_services(root, MissionMode.FULL, agent=agent)
            agent.artifacts = services.artifacts
            sessions = FilesystemMissionSessionStore(services.artifacts)
            catalog = SqliteDocumentCatalog(context.harness_dir / "documents.db")
            documents = MissionDocumentService(services.artifacts, catalog, services.events)
            control = MissionControlPlane(
                services,
                context,
                sessions,
                catalog,
                documents,
                PreparationCoordinator(
                    services=services,
                    context=context,
                    sessions=sessions,
                    documents=documents,
                    catalog=catalog,
                ),
                InteractiveTaskCoordinator(
                    services=services,
                    context=context,
                    sessions=sessions,
                    documents=documents,
                ),
            )
            server = ControlHttpServer(control, token="test-token")
            server.start()
            self.addCleanup(server.stop)

            with self.assertRaises(HTTPError) as unauthorized:
                urlopen(f"{server.base_url}/api/v1/snapshot")
            self.assertEqual(unauthorized.exception.code, 401)
            error = json.loads(unauthorized.exception.read().decode("utf-8"))
            self.assertEqual(error["code"], "unauthorized")

            with urlopen(f"{server.base_url}/api/v1/openapi.json") as response:
                contract = json.load(response)
            capabilities = self._request(server, "/api/v1/capabilities")
            self.assertEqual(contract["openapi"], "3.0.3")
            self.assertIn("/documents/{logical_id}", contract["paths"])
            self.assertTrue(capabilities["features"]["versioned_documents"])

            logical_id = quote("mission/idea", safe="")
            saved = self._request(
                server,
                f"/api/v1/documents/{logical_id}",
                method="PUT",
                body={
                    "content": "# HTTP idea\n",
                    "base_revision": 0,
                    "command_id": "http-save-1",
                },
            )
            snapshot = self._request(server, "/api/v1/snapshot")
            document = self._request(server, f"/api/v1/documents/{logical_id}")

            self.assertEqual(saved["status"], "APPLIED")
            self.assertEqual(document["content"], "# HTTP idea\n")
            self.assertEqual(snapshot["documents"][0]["revision"], 1)

    @staticmethod
    def _request(
        server: ControlHttpServer,
        path: str,
        *,
        method: str = "GET",
        body: dict | None = None,
    ) -> dict:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(
            server.base_url + path,
            data=data,
            method=method,
            headers={
                "Authorization": "Bearer test-token",
                "Content-Type": "application/json",
            },
        )
        with urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    unittest.main()