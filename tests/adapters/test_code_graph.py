from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from mission_orchestrator.adapters.analysis.builder import CodeGraphBuilder
from mission_orchestrator.adapters.analysis.sqlite_graph import SQLiteCodeGraph


def _git_available() -> bool:
    try:
        return subprocess.run(["git", "--version"], capture_output=True, timeout=10).returncode == 0
    except Exception:
        return False


class CodeGraphK1Test(unittest.TestCase):
    def setUp(self) -> None:
        self._project_tmp = tempfile.TemporaryDirectory()
        self._db_tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._project_tmp.name)
        self.graph = SQLiteCodeGraph(Path(self._db_tmp.name) / "graph.db")
        self.builder = CodeGraphBuilder(self.graph)

    def tearDown(self) -> None:
        self._project_tmp.cleanup()
        self._db_tmp.cleanup()

    def _node_ids(self) -> set[str]:
        with self.graph.session() as connection:
            return {row[0] for row in connection.execute("SELECT id FROM nodes")}

    def _revision(self) -> int:
        with self.graph.session() as connection:
            row = connection.execute(
                "SELECT value FROM meta WHERE key = 'observed_revision'"
            ).fetchone()
            return int(row[0]) if row else 0

    @unittest.skipUnless(_git_available(), "git not available")
    def test_discovery_includes_untracked_files_in_git_repo(self) -> None:
        subprocess.run(["git", "init", "-q"], cwd=self.project, check=True, timeout=30)
        (self.project / "tracked.py").write_text("def tracked_fn():\n    pass\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.py"], cwd=self.project, check=True, timeout=30)
        (self.project / "untracked.py").write_text("def new_fn():\n    pass\n", encoding="utf-8")
        self.builder.build(self.project)
        ids = self._node_ids()
        self.assertIn("tracked.py:tracked_fn", ids)
        self.assertIn("untracked.py:new_fn", ids)

    def test_deleted_file_rows_are_purged_on_rebuild(self) -> None:
        target = self.project / "temp_module.py"
        target.write_text("class Gone:\n    def method(self):\n        pass\n", encoding="utf-8")
        self.builder.build(self.project)
        self.assertIn("temp_module.py:Gone", self._node_ids())
        target.unlink()
        self.builder.build(self.project)
        ids = self._node_ids()
        self.assertNotIn("temp_module.py:Gone", ids)
        with self.graph.session() as connection:
            files = [row[0] for row in connection.execute("SELECT path FROM files")]
            edges = connection.execute(
                "SELECT COUNT(*) FROM edges WHERE file = 'temp_module.py'"
            ).fetchone()[0]
        self.assertNotIn("temp_module.py", files)
        self.assertEqual(edges, 0)

    def test_nested_scopes_get_qualified_non_colliding_ids(self) -> None:
        (self.project / "nested.py").write_text(
            "class Outer:\n"
            "    class Inner:\n"
            "        def method(self):\n"
            "            pass\n"
            "    def method(self):\n"
            "        def helper():\n"
            "            pass\n"
            "def method():\n"
            "    def helper():\n"
            "        pass\n",
            encoding="utf-8",
        )
        self.builder.build(self.project)
        ids = self._node_ids()
        self.assertIn("nested.py:Outer", ids)
        self.assertIn("nested.py:Outer.Inner", ids)
        self.assertIn("nested.py:Outer.Inner.method", ids)
        self.assertIn("nested.py:Outer.method", ids)
        self.assertIn("nested.py:Outer.method.helper", ids)
        self.assertIn("nested.py:method", ids)
        self.assertIn("nested.py:method.helper", ids)
        with self.graph.session() as connection:
            types = dict(
                connection.execute("SELECT id, type FROM nodes WHERE file = 'nested.py'")
            )
        self.assertEqual(types["nested.py:Outer.Inner.method"], "method")
        self.assertEqual(types["nested.py:method"], "function")
        self.assertEqual(types["nested.py:Outer.method.helper"], "function")

    def test_structural_edges_separated_from_lexical_refs(self) -> None:
        (self.project / "mod.py").write_text(
            "import os\n"
            "class Base:\n"
            "    pass\n"
            "class Child(Base):\n"
            "    def run(self):\n"
            "        helper(os.path)\n",
            encoding="utf-8",
        )
        self.builder.build(self.project)
        with self.graph.session() as connection:
            structural = {row[0] for row in connection.execute("SELECT DISTINCT relation FROM edges")}
            lexical = {row[0] for row in connection.execute("SELECT DISTINCT relation FROM lexical_refs")}
        self.assertEqual(structural, {"defines", "imports", "inherits"})
        self.assertTrue(lexical.issubset({"calls", "references"}))
        self.assertIn("calls", lexical)

    def test_observed_revision_bumps_only_on_change(self) -> None:
        (self.project / "a.py").write_text("def one():\n    pass\n", encoding="utf-8")
        self.builder.build(self.project)
        first = self._revision()
        self.assertGreaterEqual(first, 1)
        self.builder.build(self.project)
        self.assertEqual(self._revision(), first)
        (self.project / "a.py").write_text("def one():\n    pass\n\ndef two():\n    pass\n", encoding="utf-8")
        self.builder.build(self.project)
        self.assertEqual(self._revision(), first + 1)

    def test_dead_code_reports_unreferenced_and_spares_referenced(self) -> None:
        (self.project / "usage.py").write_text(
            "class Used:\n"
            "    pass\n"
            "class Unused:\n"
            "    pass\n"
            "def used_fn():\n"
            "    pass\n"
            "def unused_fn():\n"
            "    pass\n"
            "def main():\n"
            "    used_fn()\n"
            "    return Used()\n",
            encoding="utf-8",
        )
        self.builder.build(self.project)
        dead = set(self.graph.dead_code())
        self.assertIn("usage.py:Unused", dead)
        self.assertIn("usage.py:unused_fn", dead)
        self.assertNotIn("usage.py:Used", dead)
        self.assertNotIn("usage.py:used_fn", dead)

    def test_schema_version_reset_rebuilds_old_database(self) -> None:
        import sqlite3

        legacy = sqlite3.connect(self.graph.db_path)
        legacy.execute("CREATE TABLE IF NOT EXISTS nodes(id TEXT PRIMARY KEY, type TEXT, file TEXT)")
        legacy.execute("INSERT INTO nodes VALUES ('stale.py', 'module', 'stale.py')")
        legacy.commit()
        legacy.close()
        (self.project / "fresh.py").write_text("def fresh():\n    pass\n", encoding="utf-8")
        self.builder.build(self.project)
        ids = self._node_ids()
        self.assertNotIn("stale.py", ids)
        self.assertIn("fresh.py:fresh", ids)


if __name__ == "__main__":
    unittest.main()
