from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from mission_orchestrator.adapters.analysis.builder import CodeGraphBuilder
from mission_orchestrator.adapters.analysis.sqlite_graph import SQLiteCodeGraph
from mission_orchestrator.adapters.tools.graph_tools import CodeGraphTool, GraphProposeTool, GraphQueryTool
from mission_orchestrator.adapters.tools.registry import default_tool_registry
from mission_orchestrator.application.phase_registry import PHASES
from mission_orchestrator.domain.phase import PhaseAuthority, PhaseName
from mission_orchestrator.ports.tool_registry import ToolEnvironment


def _propose_ops(operation_id: str, base_revision: int, operations: list[dict]) -> dict:
    return {"operation_id": operation_id, "base_revision": base_revision, "operations": operations}


def _node_op(node_id: str, **overrides) -> dict:
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


class GraphToolsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._project_tmp = tempfile.TemporaryDirectory()
        self._harness_tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._project_tmp.name)
        self.harness = Path(self._harness_tmp.name)
        self.env = ToolEnvironment(self.project, self.harness)
        self.query = GraphQueryTool()
        self.code_graph = CodeGraphTool()
        self.propose = GraphProposeTool()

    def tearDown(self) -> None:
        self._project_tmp.cleanup()
        self._harness_tmp.cleanup()

    def _build_facts(self) -> None:
        (self.project / "mod.py").write_text("class Real:\n    pass\n", encoding="utf-8")
        facts = SQLiteCodeGraph(self.harness / "code_graph.db")
        CodeGraphBuilder(facts).build(self.project)

    def test_b1_empty_design_query(self) -> None:
        result = json.loads(self.query.execute({"scope": "design"}, self.env))
        self.assertEqual(result["design_revision"], 0)
        self.assertEqual(result["nodes"], [])
        self.assertEqual(result["edges"], [])

    def test_b2_propose_then_query_with_resolution(self) -> None:
        self._build_facts()
        outcome = json.loads(
            self.propose.execute(
                _propose_ops(
                    "op-1",
                    0,
                    [
                        _node_op("existing", locator="mod.py:Real", intent="KEEP"),
                        _node_op("proposed", locator="mod.py:NotYet"),
                        _node_op("db_pg", level="SYSTEM", location="EXTERNAL", intent="KEEP"),
                        {
                            "op": "add_edge",
                            "source": "existing",
                            "target": "db_pg",
                            "relation": "uses",
                            "provenance": "AGENT",
                            "intent": "CREATE",
                        },
                    ],
                ),
                self.env,
            )
        )
        self.assertEqual(outcome["status"], "APPLIED")
        self.assertEqual(outcome["design_revision"], 1)
        view = json.loads(self.query.execute({"scope": "design"}, self.env))
        nodes = {node["id"]: node for node in view["nodes"]}
        self.assertEqual(nodes["existing"]["resolution"], "RESOLVED")
        self.assertEqual(nodes["proposed"]["resolution"], "UNRESOLVED")
        self.assertEqual(nodes["db_pg"]["resolution"], "EXTERNAL")
        self.assertEqual(len(view["edges"]), 1)

    def test_b3_stale_revision_conflict_reports_current(self) -> None:
        self.propose.execute(_propose_ops("op-1", 0, [_node_op("n1")]), self.env)
        outcome = json.loads(
            self.propose.execute(_propose_ops("op-2", 0, [_node_op("n2")]), self.env)
        )
        self.assertEqual(outcome["status"], "CONFLICT")
        self.assertEqual(outcome["design_revision"], 1)
        view = json.loads(self.query.execute({"scope": "design"}, self.env))
        self.assertEqual({node["id"] for node in view["nodes"]}, {"n1"})

    def test_graph_proposal_during_execution_requests_a_safe_boundary_amendment(self) -> None:
        (self.harness / "_session.json").write_text(
            json.dumps({"stage": "executing", "revision": 7}), encoding="utf-8"
        )

        self.propose.execute(_propose_ops("op-amend", 0, [_node_op("n1")]), self.env)

        pending = json.loads((self.harness / "_amendment_pending.json").read_text(encoding="utf-8"))
        self.assertEqual(pending["design_revision"], 1)
        self.assertEqual(pending["source"], "mission_graph_proposal")

    def test_b4_invalid_operation_rejected_with_detail(self) -> None:
        outcome = json.loads(
            self.propose.execute(
                _propose_ops("op-1", 0, [{"op": "teleport", "id": "x"}]), self.env
            )
        )
        self.assertEqual(outcome["status"], "REJECTED")
        self.assertIn("teleport", outcome["detail"])
        view = json.loads(self.query.execute({"scope": "design"}, self.env))
        self.assertEqual(view["nodes"], [])

    def test_b5_duplicate_operation_id(self) -> None:
        self.propose.execute(_propose_ops("op-1", 0, [_node_op("n1")]), self.env)
        outcome = json.loads(
            self.propose.execute(_propose_ops("op-1", 1, [_node_op("n1")]), self.env)
        )
        self.assertEqual(outcome["status"], "DUPLICATE")
        self.assertEqual(outcome["design_revision"], 1)

    def test_b6_facts_pattern_search(self) -> None:
        self._build_facts()
        result = json.loads(self.query.execute({"scope": "facts", "pattern": "Real"}, self.env))
        ids = {match["id"] for match in result["matches"]}
        self.assertIn("mod.py:Real", ids)

    def test_o1_code_graph_is_bounded_and_reads_the_fixed_mission_db(self) -> None:
        (self.project / "mod.py").write_text(
            "class Base:\n    pass\n\nclass Child(Base):\n    pass\n",
            encoding="utf-8",
        )
        facts = SQLiteCodeGraph(self.harness / "code_graph.db")
        CodeGraphBuilder(facts).build(self.project)
        result = json.loads(self.code_graph.execute({"action": "dependencies", "node": "mod.py"}, self.env))
        self.assertEqual(result["columns"], ["relation", "type", "id", "file"])
        self.assertEqual(
            result["rows"],
            [
                ["defines", "class", "mod.py:Base", "mod.py"],
                ["defines", "class", "mod.py:Child", "mod.py"],
            ],
        )
        self.assertGreater(result["observed_revision"], 0)
        with self.assertRaises(ValueError):
            self.code_graph.execute({"action": "dead_code", "db": "outside.db"}, self.env)
        with self.assertRaises(ValueError):
            self.code_graph.execute({"action": "find_nodes", "pattern": "Base", "limit": 201}, self.env)

    def test_b7_registration_and_phase_wiring(self) -> None:
        registry = default_tool_registry()
        schemas = registry.schemas_for(
            PhaseAuthority(
                PhaseName.RESEARCH,
                ("CodeGraph", "GraphQuery", "GraphPropose"),
                harness_mutation_tools=("GraphPropose",),
            )
        )
        self.assertEqual({schema["name"] for schema in schemas}, {"CodeGraph", "GraphQuery", "GraphPropose"})
        for phase in (PhaseName.RESEARCH, PhaseName.GRILL):
            self.assertIn("CodeGraph", PHASES[phase].tools)
            self.assertIn("GraphQuery", PHASES[phase].tools)
            self.assertIn("GraphPropose", PHASES[phase].tools)
        for phase in (PhaseName.RESEARCH, PhaseName.GRILL, PhaseName.IMPLEMENT, PhaseName.IMPLEMENT_BURSTS, PhaseName.REIMPLEMENT):
            self.assertIn("GraphPropose", PHASES[phase].tools)
        for phase in (PhaseName.SPEC, PhaseName.PLAN, PhaseName.REVIEW):
            self.assertNotIn("GraphPropose", PHASES[phase].tools)

    def test_b8_design_filters(self) -> None:
        self.propose.execute(
            _propose_ops(
                "op-1",
                0,
                [
                    _node_op("sys1", level="SYSTEM", intent="KEEP"),
                    _node_op("code1", intent="CHANGE"),
                ],
            ),
            self.env,
        )
        by_level = json.loads(self.query.execute({"scope": "design", "level": "SYSTEM"}, self.env))
        self.assertEqual({node["id"] for node in by_level["nodes"]}, {"sys1"})
        by_intent = json.loads(self.query.execute({"scope": "design", "intent": "CHANGE"}, self.env))
        self.assertEqual({node["id"] for node in by_intent["nodes"]}, {"code1"})


if __name__ == "__main__":
    unittest.main()
