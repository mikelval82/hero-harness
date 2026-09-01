from __future__ import annotations

from pathlib import Path

from mission_orchestrator.adapters.analysis.builder import CodeGraphBuilder
from mission_orchestrator.adapters.analysis.sqlite_graph import SQLiteCodeGraph


class SQLiteCodeGraphService:
    def __init__(self, harness_dir: Path) -> None:
        self.graph = SQLiteCodeGraph(harness_dir / "code_graph.db")
        self.builder = CodeGraphBuilder(self.graph)

    def build(self, project_dir: Path) -> None:
        self.builder.build(project_dir)

