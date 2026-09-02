from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from mission_orchestrator.domain.changeset import changeset_to_json, compile_changeset


def _snapshot(nodes: list[dict], edges: list[dict] | None = None, snapshot_id: str = "snap-1") -> dict:
    return {
        "snapshot_id": snapshot_id,
        "design_revision": 1,
        "observed_revision": 1,
        "nodes": nodes,
        "edges": edges or [],
    }


def _node(node_id: str, intent: str, **overrides) -> dict:
    base = {
        "id": node_id,
        "label": node_id,
        "level": "CODE",
        "provenance": "AGENT",
        "location": "IN_REPOSITORY",
        "intent": intent,
        "parent_id": None,
        "locator": None,
        "description": "",
    }
    base.update(overrides)
    return base


class ChangesetCompilerTest(unittest.TestCase):
    def test_c1_create_emits_operation_and_keep_is_context(self) -> None:
        result = compile_changeset(
            _snapshot([_node("cache", "CREATE", locator="src/cache.py:Cache"), _node("api", "KEEP", locator="src/api.py:Api")]),
            observed_ids={"src/api.py:Api"},
        )
        self.assertEqual([op.id for op in result.operations], ["create:cache"])
        op = result.operations[0]
        self.assertEqual(op.kind, "CREATE_NODE")
        self.assertEqual(op.target_node, "cache")
        self.assertEqual(op.locator, "src/cache.py:Cache")
        self.assertEqual(result.issues, ())
        self.assertEqual(result.skipped, ())

    def test_c2_create_already_materialized_is_skipped(self) -> None:
        result = compile_changeset(
            _snapshot([_node("cache", "CREATE", locator="src/cache.py:Cache")]),
            observed_ids={"src/cache.py:Cache"},
        )
        self.assertEqual(result.operations, ())
        self.assertEqual(len(result.skipped), 1)
        self.assertEqual(result.skipped[0].target_node, "cache")
        self.assertEqual(result.skipped[0].reason, "already_materialized")

    def test_c3_change_requires_resolved_locator(self) -> None:
        resolved = compile_changeset(
            _snapshot([_node("api", "CHANGE", locator="src/api.py:Api")]),
            observed_ids={"src/api.py:Api"},
        )
        self.assertEqual([op.id for op in resolved.operations], ["change:api"])
        self.assertEqual(resolved.operations[0].kind, "MODIFY_NODE")

        without_locator = compile_changeset(
            _snapshot([_node("api", "CHANGE")]), observed_ids=set()
        )
        self.assertEqual(without_locator.operations, ())
        self.assertEqual(len(without_locator.issues), 1)

        unresolved = compile_changeset(
            _snapshot([_node("api", "CHANGE", locator="src/api.py:Gone")]), observed_ids=set()
        )
        self.assertEqual(unresolved.operations, ())
        self.assertEqual(len(unresolved.issues), 1)
        self.assertIn("api", unresolved.issues[0].target_node)

    def test_c4_remove_requires_resolved_locator(self) -> None:
        resolved = compile_changeset(
            _snapshot([_node("legacy", "REMOVE", locator="src/legacy.py")]),
            observed_ids={"src/legacy.py"},
        )
        self.assertEqual([op.id for op in resolved.operations], ["remove:legacy"])
        self.assertEqual(resolved.operations[0].kind, "REMOVE_NODE")

        unresolved = compile_changeset(
            _snapshot([_node("legacy", "REMOVE", locator="src/legacy.py")]), observed_ids=set()
        )
        self.assertEqual(unresolved.operations, ())
        self.assertEqual(len(unresolved.issues), 1)

    def test_c5_edge_operations_and_structural_dependencies(self) -> None:
        result = compile_changeset(
            _snapshot(
                [
                    _node("api", "CREATE", locator="src/api.py:Api"),
                    _node("cache", "CREATE", locator="src/cache.py:Cache"),
                    _node("db", "KEEP", locator="src/db.py:Db"),
                    _node("queue", "KEEP", locator="src/queue.py:Q"),
                ],
                edges=[
                    {"source": "api", "target": "cache", "relation": "uses", "provenance": "AGENT", "intent": "CREATE"},
                    {"source": "api", "target": "db", "relation": "reads", "provenance": "AGENT", "intent": "KEEP"},
                    {"source": "db", "target": "queue", "relation": "feeds", "provenance": "AGENT", "intent": "REMOVE"},
                ],
            ),
            observed_ids={"src/db.py:Db", "src/queue.py:Q"},
        )
        ids = [op.id for op in result.operations]
        self.assertIn("connect:api->cache:uses", ids)
        self.assertIn("disconnect:db->queue:feeds", ids)
        self.assertNotIn("connect:api->db:reads", ids)
        connect = next(op for op in result.operations if op.id == "connect:api->cache:uses")
        self.assertEqual(set(connect.depends_on), {"create:api", "create:cache"})

    def test_c6_determinism_regardless_of_input_order(self) -> None:
        nodes = [
            _node("b_node", "CREATE"),
            _node("a_node", "CREATE"),
            _node("c_node", "CHANGE", locator="src/c.py:C"),
        ]
        observed = {"src/c.py:C"}
        forward = compile_changeset(_snapshot(nodes), observed_ids=observed)
        backward = compile_changeset(_snapshot(list(reversed(nodes))), observed_ids=observed)
        self.assertEqual(changeset_to_json(forward), changeset_to_json(backward))
        self.assertEqual(
            [op.id for op in forward.operations],
            sorted(op.id for op in forward.operations),
        )

    def test_c7_changeset_carries_snapshot_id(self) -> None:
        result = compile_changeset(_snapshot([_node("x", "CREATE")], snapshot_id="abc123"), observed_ids=set())
        self.assertEqual(result.snapshot_id, "abc123")

    def test_c8_external_create_is_real_work(self) -> None:
        result = compile_changeset(
            _snapshot([_node("redis", "CREATE", level="SYSTEM", location="EXTERNAL")]),
            observed_ids=set(),
        )
        self.assertEqual([op.id for op in result.operations], ["create:redis"])
        self.assertEqual(result.operations[0].location, "EXTERNAL")
        self.assertEqual(result.issues, ())

    def test_c9_create_without_locator_derives_from_pathlike_label(self) -> None:
        result = compile_changeset(
            _snapshot([_node("case-index-py", "CREATE", label="tools/case_index.py")]),
            observed_ids=set(),
        )
        self.assertEqual([op.id for op in result.operations], ["create:case-index-py"])
        self.assertEqual(result.operations[0].locator, "tools/case_index.py")

    def test_cde_a06_create_derives_nested_targets_from_parent_module(self) -> None:
        result = compile_changeset(
            _snapshot(
                [
                    _node(
                        "package",
                        "KEEP",
                        level="PACKAGE",
                        locator="src/hero_graph_lab/__init__.py",
                    ),
                    _node(
                        "adapter",
                        "CREATE",
                        label="markdown_adapter.py",
                        kind="module",
                        level="PACKAGE",
                        parent_id="package",
                    ),
                    _node(
                        "extractor",
                        "CREATE",
                        label="MarkdownGraphExtractor",
                        kind="class",
                        parent_id="adapter",
                    ),
                    _node(
                        "extract",
                        "CREATE",
                        label="extract_markdown_graph(root, markdown_files)",
                        kind="function",
                        parent_id="adapter",
                    ),
                ]
            ),
            observed_ids={"src/hero_graph_lab/__init__.py"},
        )

        self.assertEqual(result.issues, ())
        operations = {operation.target_node: operation for operation in result.operations}
        self.assertEqual(operations["adapter"].target_path, "src/hero_graph_lab/markdown_adapter.py")
        self.assertEqual(operations["adapter"].locator, "src/hero_graph_lab/markdown_adapter.py")
        self.assertEqual(operations["extractor"].target_path, "src/hero_graph_lab/markdown_adapter.py")
        self.assertEqual(operations["extractor"].locator, "src/hero_graph_lab/markdown_adapter.py:MarkdownGraphExtractor")
        self.assertEqual(operations["extract"].locator, "src/hero_graph_lab/markdown_adapter.py:extract_markdown_graph")

    def test_c10_create_with_prose_label_keeps_locator_none(self) -> None:
        result = compile_changeset(
            _snapshot(
                [
                    _node(
                        "cache",
                        "CREATE",
                        label="Cache layer for API",
                        kind="class",
                    )
                ]
            ),
            observed_ids=set(),
        )
        self.assertEqual(result.operations, ())
        self.assertEqual(len(result.issues), 1)
        self.assertIn("target_path", result.issues[0].detail)

    def test_c11_derived_locator_counts_for_materialization(self) -> None:
        result = compile_changeset(
            _snapshot([_node("case-index-py", "CREATE", label="tools/case_index.py")]),
            observed_ids={"tools/case_index.py"},
        )
        self.assertEqual(result.operations, ())
        self.assertEqual([item.reason for item in result.skipped], ["already_materialized"])

    def test_cde_a05_preserves_exact_node_contract_and_derives_locator(self) -> None:
        result = compile_changeset(
            _snapshot(
                [
                    _node(
                        "notifier",
                        "CREATE",
                        kind="class",
                        target_path="src/telegram/notifier.py",
                        qualified_name="TelegramNotifier",
                        signature="",
                        docstring="Send notifications through Telegram.",
                        satisfies=["REQ-7", "REQ-2"],
                        acceptance=["A message is delivered", "Errors are surfaced"],
                    )
                ]
            ),
            observed_ids=set(),
        )

        self.assertEqual(result.issues, ())
        operation = result.operations[0]
        self.assertEqual(operation.locator, "src/telegram/notifier.py:TelegramNotifier")
        self.assertEqual(operation.node_kind, "class")
        self.assertEqual(operation.target_path, "src/telegram/notifier.py")
        self.assertEqual(operation.qualified_name, "TelegramNotifier")
        self.assertEqual(operation.docstring, "Send notifications through Telegram.")
        self.assertEqual(operation.satisfies, ("REQ-7", "REQ-2"))
        self.assertEqual(
            operation.acceptance,
            ("A message is delivered", "Errors are surfaced"),
        )
        encoded = json.loads(changeset_to_json(result))["operations"][0]
        self.assertEqual(encoded["node_kind"], "class")
        self.assertEqual(encoded["satisfies"], ["REQ-7", "REQ-2"])

    def test_cde_a05_classifies_relationship_verification(self) -> None:
        result = compile_changeset(
            _snapshot(
                [
                    _node(
                        "module",
                        "CREATE",
                        kind="module",
                        target_path="src/telegram/notifier.py",
                    ),
                    _node(
                        "notifier",
                        "CREATE",
                        kind="class",
                        target_path="src/telegram/notifier.py",
                        qualified_name="TelegramNotifier",
                    ),
                ],
                edges=[
                    {
                        "source": "module",
                        "target": "notifier",
                        "relation": "contains",
                        "provenance": "AGENT",
                        "intent": "CREATE",
                    }
                ],
            ),
            observed_ids=set(),
        )

        operation = next(op for op in result.operations if op.kind == "CONNECT")
        self.assertEqual(operation.source, "module")
        self.assertEqual(operation.target, "notifier")
        self.assertEqual(operation.relation, "contains")
        self.assertEqual(operation.verification_level, "hard")


if __name__ == "__main__":
    unittest.main()
