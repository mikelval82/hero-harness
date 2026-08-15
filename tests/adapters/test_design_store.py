from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from mission_orchestrator.adapters.analysis.builder import CodeGraphBuilder
from mission_orchestrator.adapters.analysis.sqlite_graph import SQLiteCodeGraph
from mission_orchestrator.adapters.design.store import DesignStore, DesignStoreVersionError
from mission_orchestrator.domain.design import ApplyStatus, Resolution


def _node(node_id: str, **overrides) -> dict:
    base = {
        "op": "add_node",
        "id": node_id,
        "label": node_id,
        "level": "CODE",
        "provenance": "AGENT",
        "location": "IN_REPOSITORY",
        "intent": "CREATE",
    }
    base.update(overrides)
    return base


class DesignStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = DesignStore(Path(self._tmp.name) / "design.db")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_a1_apply_adds_nodes_and_edges_and_bumps_revision(self) -> None:
        result = self.store.apply(
            operation_id="op-1",
            author="AGENT:researcher",
            base_revision=0,
            operations=[
                _node("svc_api", level="SYSTEM", provenance="HUMAN", intent="KEEP"),
                _node("cache_redis", level="SYSTEM"),
                {
                    "op": "add_edge",
                    "source": "svc_api",
                    "target": "cache_redis",
                    "relation": "uses",
                    "provenance": "AGENT",
                    "intent": "CREATE",
                },
            ],
        )
        self.assertEqual(result.status, ApplyStatus.APPLIED)
        self.assertEqual(result.revision, 1)
        self.assertEqual(self.store.current_revision(), 1)
        nodes = {node.id: node for node in self.store.nodes()}
        self.assertEqual(nodes["svc_api"].provenance, "HUMAN")
        self.assertEqual(nodes["svc_api"].intent, "KEEP")
        self.assertEqual(nodes["cache_redis"].location, "IN_REPOSITORY")
        edges = self.store.edges()
        self.assertEqual(len(edges), 1)
        self.assertEqual((edges[0].source, edges[0].target, edges[0].relation), ("svc_api", "cache_redis", "uses"))

    def test_a2_stale_base_revision_is_conflict(self) -> None:
        self.store.apply(operation_id="op-1", author="a", base_revision=0, operations=[_node("n1")])
        result = self.store.apply(
            operation_id="op-2", author="b", base_revision=0, operations=[_node("n2")]
        )
        self.assertEqual(result.status, ApplyStatus.CONFLICT)
        self.assertEqual(self.store.current_revision(), 1)
        self.assertEqual({node.id for node in self.store.nodes()}, {"n1"})

    def test_a3_duplicate_operation_id_returns_original_without_reapplying(self) -> None:
        first = self.store.apply(
            operation_id="op-1", author="a", base_revision=0, operations=[_node("n1")]
        )
        replay = self.store.apply(
            operation_id="op-1", author="a", base_revision=1, operations=[_node("n1")]
        )
        self.assertEqual(replay.status, ApplyStatus.DUPLICATE)
        self.assertEqual(replay.revision, first.revision)
        self.assertEqual(self.store.current_revision(), 1)
        self.assertEqual(len(self.store.nodes()), 1)

    def test_a4_batch_is_atomic(self) -> None:
        result = self.store.apply(
            operation_id="op-1",
            author="a",
            base_revision=0,
            operations=[
                _node("valid_node"),
                {
                    "op": "add_edge",
                    "source": "valid_node",
                    "target": "missing_node",
                    "relation": "uses",
                    "provenance": "AGENT",
                    "intent": "CREATE",
                },
            ],
        )
        self.assertEqual(result.status, ApplyStatus.REJECTED)
        self.assertEqual(self.store.current_revision(), 0)
        self.assertEqual(self.store.nodes(), [])

    def test_a5_validation_rejections(self) -> None:
        update_missing = self.store.apply(
            operation_id="op-1",
            author="a",
            base_revision=0,
            operations=[{"op": "update_node", "id": "ghost", "label": "x"}],
        )
        self.assertEqual(update_missing.status, ApplyStatus.REJECTED)
        unknown_op = self.store.apply(
            operation_id="op-2",
            author="a",
            base_revision=0,
            operations=[{"op": "teleport_node", "id": "n"}],
        )
        self.assertEqual(unknown_op.status, ApplyStatus.REJECTED)
        self.store.apply(operation_id="op-3", author="a", base_revision=0, operations=[_node("n1")])
        provenance_change = self.store.apply(
            operation_id="op-4",
            author="a",
            base_revision=1,
            operations=[{"op": "update_node", "id": "n1", "provenance": "HUMAN"}],
        )
        self.assertEqual(provenance_change.status, ApplyStatus.REJECTED)

    def test_a6_resolution_is_computed_against_facts(self) -> None:
        with tempfile.TemporaryDirectory() as project_dir, tempfile.TemporaryDirectory() as db_dir:
            project = Path(project_dir)
            (project / "mod.py").write_text("class Real:\n    pass\n", encoding="utf-8")
            facts = SQLiteCodeGraph(Path(db_dir) / "facts.db")
            CodeGraphBuilder(facts).build(project)
            self.store.apply(
                operation_id="op-1",
                author="a",
                base_revision=0,
                operations=[
                    _node("existing", locator="mod.py:Real", intent="KEEP"),
                    _node("proposed", locator="mod.py:NotYet"),
                    _node("db_pg", level="SYSTEM", location="EXTERNAL", intent="KEEP"),
                ],
            )
            nodes = {node.id: node for node in self.store.nodes()}
            self.assertEqual(self.store.resolution_for(nodes["existing"], facts), Resolution.RESOLVED)
            self.assertEqual(self.store.resolution_for(nodes["proposed"], facts), Resolution.UNRESOLVED)
            self.assertEqual(self.store.resolution_for(nodes["db_pg"], facts), Resolution.EXTERNAL)

    def test_a7_history_records_every_attempt(self) -> None:
        self.store.apply(operation_id="op-1", author="human", base_revision=0, operations=[_node("n1")])
        self.store.apply(operation_id="op-2", author="agent", base_revision=0, operations=[_node("n2")])
        self.store.apply(
            operation_id="op-3",
            author="agent",
            base_revision=1,
            operations=[{"op": "update_node", "id": "ghost", "label": "x"}],
        )
        history = self.store.history()
        self.assertEqual(
            [(record.operation_id, record.author, record.base_revision, record.status) for record in history],
            [
                ("op-1", "human", 0, ApplyStatus.APPLIED),
                ("op-2", "agent", 0, ApplyStatus.CONFLICT),
                ("op-3", "agent", 1, ApplyStatus.REJECTED),
            ],
        )

    def test_a8_version_mismatch_raises_and_preserves_data(self) -> None:
        self.store.apply(operation_id="op-1", author="a", base_revision=0, operations=[_node("n1")])
        db_path = self.store.db_path
        raw = sqlite3.connect(db_path)
        raw.execute("PRAGMA user_version = 99")
        raw.commit()
        raw.close()
        with self.assertRaises(DesignStoreVersionError):
            DesignStore(db_path).current_revision()
        raw = sqlite3.connect(db_path)
        count = raw.execute("SELECT COUNT(*) FROM design_nodes").fetchone()[0]
        raw.close()
        self.assertEqual(count, 1)

    def test_a9_query_filters(self) -> None:
        self.store.apply(
            operation_id="op-1",
            author="a",
            base_revision=0,
            operations=[
                _node("sys1", level="SYSTEM", intent="KEEP"),
                _node("pkg1", level="PACKAGE", parent_id="sys1"),
                _node("code1", level="CODE", parent_id="pkg1", intent="CHANGE"),
            ],
        )
        self.assertEqual({n.id for n in self.store.nodes(level="SYSTEM")}, {"sys1"})
        self.assertEqual({n.id for n in self.store.nodes(parent_id="pkg1")}, {"code1"})
        self.assertEqual({n.id for n in self.store.nodes(intent="CHANGE")}, {"code1"})

    def test_cde_a01_migrates_v1_without_losing_authorial_data(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            db_path = Path(raw) / "design.db"
            connection = sqlite3.connect(db_path)
            connection.executescript(
                """
                CREATE TABLE design_nodes(
                  id TEXT PRIMARY KEY, label TEXT NOT NULL, level TEXT NOT NULL,
                  provenance TEXT NOT NULL, location TEXT NOT NULL, intent TEXT NOT NULL,
                  parent_id TEXT, locator TEXT, description TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE design_meta(key TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE operations(
                  seq INTEGER PRIMARY KEY AUTOINCREMENT, operation_id TEXT UNIQUE NOT NULL,
                  author TEXT NOT NULL, ts TEXT NOT NULL, base_revision INTEGER NOT NULL,
                  ops_json TEXT NOT NULL, status TEXT NOT NULL,
                  result_revision INTEGER NOT NULL, detail TEXT NOT NULL DEFAULT ''
                );
                INSERT INTO design_nodes VALUES(
                  'legacy', 'LegacyThing', 'CODE', 'HUMAN', 'IN_REPOSITORY',
                  'CREATE', NULL, 'legacy.py:LegacyThing', 'Keep this decision'
                );
                INSERT INTO design_meta VALUES('design_revision', '3');
                INSERT INTO operations(
                  operation_id, author, ts, base_revision, ops_json, status,
                  result_revision, detail
                ) VALUES('legacy-op', 'HUMAN', '2026-08-15', 2, '[]', 'APPLIED', 3, '');
                PRAGMA user_version = 1;
                """
            )
            connection.commit()
            connection.close()

            migrated = DesignStore(db_path)
            node = migrated.nodes()[0]

            self.assertEqual(migrated.current_revision(), 3)
            self.assertEqual(node.id, "legacy")
            self.assertEqual(node.description, "Keep this decision")
            self.assertEqual(node.kind, "unknown")
            self.assertEqual(node.satisfies, ())
            self.assertEqual(migrated.history()[0].operation_id, "legacy-op")
            verified = sqlite3.connect(db_path)
            self.assertEqual(verified.execute("PRAGMA user_version").fetchone()[0], 2)
            verified.close()

    def test_cde_node_contract_roundtrips_and_is_snapshotted(self) -> None:
        result = self.store.apply(
            operation_id="contract-1",
            author="HUMAN",
            base_revision=0,
            operations=[
                _node(
                    "telegram_gateway",
                    kind="class",
                    target_path="src/app/telegram/gateway.py",
                    qualified_name="TelegramGateway",
                    docstring="Telegram transport boundary.",
                    satisfies=["BR-002"],
                    acceptance=["SDK types do not escape the adapter."],
                ),
                _node(
                    "send_notification",
                    kind="method",
                    parent_id="telegram_gateway",
                    target_path="src/app/telegram/gateway.py",
                    qualified_name="TelegramGateway.send_notification",
                    signature="send_notification(self, chat_id: str, text: str) -> str",
                    docstring="Send one notification.",
                    satisfies=["BR-002"],
                ),
            ],
        )

        self.assertEqual(result.status, ApplyStatus.APPLIED)
        nodes = {node.id: node for node in self.store.nodes()}
        self.assertEqual(nodes["telegram_gateway"].kind, "class")
        self.assertEqual(nodes["telegram_gateway"].target_path, "src/app/telegram/gateway.py")
        self.assertEqual(nodes["telegram_gateway"].satisfies, ("BR-002",))
        self.assertEqual(
            nodes["send_notification"].signature,
            "send_notification(self, chat_id: str, text: str) -> str",
        )
        snapshot = self.store.approve(base_revision=1, observed_revision=4).snapshot
        stored = {node["id"]: node for node in snapshot["nodes"]}
        self.assertEqual(stored["telegram_gateway"]["kind"], "class")
        self.assertEqual(stored["telegram_gateway"]["acceptance"], ["SDK types do not escape the adapter."])

    def test_cde_new_contract_cannot_explicitly_use_unknown_kind(self) -> None:
        result = self.store.apply(
            operation_id="unknown-kind",
            author="AGENT",
            base_revision=0,
            operations=[_node("ambiguous", kind="unknown")],
        )

        self.assertEqual(result.status, ApplyStatus.REJECTED)
        self.assertIn("exact kind", result.detail)


if __name__ == "__main__":
    unittest.main()
