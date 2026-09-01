from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from mission_orchestrator.application.markdown_contracts import audit_verdict, status_files
from mission_orchestrator.application.review_evidence import ReviewEvidence
from mission_orchestrator.ports.artifacts import ArtifactStore
from mission_orchestrator.ports.git_service import GitService


class ReviewReceiptWriter:
    """Creates a runtime-owned summary after independent verification."""

    def __init__(self, artifacts: ArtifactStore, git: GitService) -> None:
        self.artifacts = artifacts
        self.git = git

    def write(self) -> None:
        audit = self.artifacts.read_text("audit.md")
        evidence = ReviewEvidence.from_json(self.artifacts.read_text("review-evidence.json"))
        status = self.artifacts.read_text("status.md", default="")
        contract = self.artifacts.read_text("task-contract.json", default="")
        verification = self.artifacts.read_text("contract-verification.json", default="")
        payload = {
            "schema_version": 1,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "verdict": audit_verdict(audit),
            "audit": self._reference("audit.md", audit),
            "task_contract": self._reference("task-contract.json", contract),
            "contract_verification": self._reference("contract-verification.json", verification),
            "validation_evidence": self._validation_receipts(contract),
            "declared_scope": [path.as_posix() for path in status_files(status)],
            "observed_workspace_changes": self.git.changed_files(),
            "review_evidence": evidence.to_json(),
        }
        self.artifacts.write_text("review-receipt.json", json.dumps(payload, indent=2, sort_keys=True) + "\n")

    def _validation_receipts(self, contract: str) -> list[dict[str, object]]:
        try:
            obligations = json.loads(contract).get("validation_obligations", []) if contract else []
        except json.JSONDecodeError:
            obligations = []
        result = []
        for check_id in sorted({str(item.get("check_id")) for item in obligations if item.get("check_id")}):
            name = f"validation-evidence/{check_id}.json"
            result.append(self._reference(name, self.artifacts.read_text(name, default="")))
        return result

    @staticmethod
    def _reference(name: str, content: str) -> dict[str, object]:
        return {"artifact": name, "exists": bool(content), "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest()}
