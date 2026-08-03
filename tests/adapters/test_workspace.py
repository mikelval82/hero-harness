from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from mission_orchestrator.adapters.filesystem.workspace import WorkspaceManager
from mission_orchestrator.domain.mission import GateMode


class WorkspaceScopesTest(unittest.TestCase):
    def setUp(self) -> None:
        self._root_tmp = tempfile.TemporaryDirectory()
        self._projects_tmp = tempfile.TemporaryDirectory()
        self.manager = WorkspaceManager(root=Path(self._root_tmp.name))

    def tearDown(self) -> None:
        self._root_tmp.cleanup()
        self._projects_tmp.cleanup()

    def _project(self, name: str) -> Path:
        path = Path(self._projects_tmp.name) / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _setup(self, project: Path, *, branch: str = "feature-x", resume: bool = False):
        return self.manager.setup(
            project_dir=project,
            branch=branch,
            resume=resume,
            gate_mode=GateMode.AUTO,
        )

    def test_same_path_yields_stable_project_id(self) -> None:
        project = self._project("app")
        first = self._setup(project)
        second = self._setup(project, branch="other-branch")
        self.assertEqual(first.project_id, second.project_id)
        self.assertEqual(first.project_scope_dir, second.project_scope_dir)

    def test_same_name_different_paths_do_not_share_state(self) -> None:
        project_a = self._project("app")
        project_b = Path(self._projects_tmp.name) / "elsewhere" / "app"
        project_b.mkdir(parents=True)
        info_a = self._setup(project_a)
        info_b = self._setup(project_b)
        self.assertNotEqual(info_a.project_id, info_b.project_id)
        self.assertNotEqual(info_a.harness_dir, info_b.harness_dir)
        self.assertNotEqual(info_a.project_scope_dir, info_b.project_scope_dir)

    def test_resume_with_manifest_but_without_tasks_keeps_state(self) -> None:
        project = self._project("app")
        info = self._setup(project)
        (info.harness_dir / "brainstorm.md").write_text("work in progress", encoding="utf-8")
        resumed = self._setup(project, resume=True)
        self.assertEqual(resumed.harness_dir, info.harness_dir)
        self.assertTrue((resumed.harness_dir / "brainstorm.md").exists())

    def test_fresh_start_wipes_mission_but_not_project_scope(self) -> None:
        project = self._project("app")
        info = self._setup(project)
        (info.harness_dir / "stale.md").write_text("old mission", encoding="utf-8")
        (info.project_scope_dir / "baseline.db").write_text("durable", encoding="utf-8")
        fresh = self._setup(project)
        self.assertFalse((fresh.harness_dir / "stale.md").exists())
        self.assertTrue((fresh.project_scope_dir / "baseline.db").exists())

    def test_manifest_records_identity(self) -> None:
        project = self._project("app")
        info = self._setup(project, branch="feat/scope")
        manifest = json.loads((info.harness_dir / "_mission.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["project_id"], info.project_id)
        self.assertEqual(Path(manifest["project_dir"]), project.resolve())
        self.assertEqual(manifest["branch"], "feat/scope")


if __name__ == "__main__":
    unittest.main()
