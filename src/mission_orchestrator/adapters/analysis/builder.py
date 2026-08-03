from __future__ import annotations

import ast
import subprocess
from dataclasses import dataclass
from pathlib import Path

from mission_orchestrator.adapters.analysis.sqlite_graph import SQLiteCodeGraph


@dataclass(frozen=True)
class Node:
    id: str
    type: str
    file: str


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    relation: str


class CodeGraphBuilder:
    def __init__(self, graph: SQLiteCodeGraph) -> None:
        self.graph = graph

    def build(self, root_dir: Path, *, force: bool = False) -> None:
        root = root_dir.resolve()
        files = self._discover_python_files(root)
        with self.graph.connect() as connection:
            for path in files:
                rel = path.relative_to(root).as_posix()
                mtime = path.stat().st_mtime_ns
                current = connection.execute("SELECT mtime_ns FROM files WHERE path = ?", (rel,)).fetchone()
                if current and int(current[0]) == mtime and not force:
                    continue
                connection.execute("DELETE FROM edges WHERE source IN (SELECT id FROM nodes WHERE file = ?)", (rel,))
                connection.execute("DELETE FROM edges WHERE target IN (SELECT id FROM nodes WHERE file = ?)", (rel,))
                connection.execute("DELETE FROM nodes WHERE file = ?", (rel,))
                nodes, edges = self._parse_file(path, rel)
                connection.executemany(
                    "INSERT OR REPLACE INTO nodes(id, type, file) VALUES (?, ?, ?)",
                    [(node.id, node.type, node.file) for node in nodes],
                )
                connection.executemany(
                    "INSERT OR IGNORE INTO edges(source, target, relation) VALUES (?, ?, ?)",
                    [(edge.source, edge.target, edge.relation) for edge in edges],
                )
                connection.execute(
                    "INSERT OR REPLACE INTO files(path, mtime_ns) VALUES (?, ?)",
                    (rel, mtime),
                )
            self.graph.rebuild_fts(connection)

    def _discover_python_files(self, root: Path) -> list[Path]:
        try:
            result = subprocess.run(
                ["git", "ls-files", "*.py"],
                cwd=root,
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
        except Exception:
            result = None
        if result and result.returncode == 0 and result.stdout.strip():
            return [root / line for line in result.stdout.splitlines()]
        return [path for path in root.rglob("*.py") if ".venv" not in path.parts and ".git" not in path.parts]

    def _parse_file(self, path: Path, rel: str) -> tuple[list[Node], list[Edge]]:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            return [Node(rel, "module", rel)], []
        nodes = [Node(rel, "module", rel)]
        edges: list[Edge] = []
        visitor = _GraphVisitor(rel, nodes, edges)
        visitor.visit(tree)
        return nodes, edges


class _GraphVisitor(ast.NodeVisitor):
    def __init__(self, rel: str, nodes: list[Node], edges: list[Edge]) -> None:
        self.rel = rel
        self.nodes = nodes
        self.edges = edges
        self.class_stack: list[str] = []
        self.scope_stack: list[str] = [rel]

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.edges.append(Edge(self.scope_stack[-1], alias.name, "imports"))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = "." * node.level + (node.module or "")
        self.edges.append(Edge(self.scope_stack[-1], module, "imports"))

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        node_id = f"{self.rel}:{node.name}"
        self.nodes.append(Node(node_id, "class", self.rel))
        self.edges.append(Edge(self.rel, node_id, "defines"))
        for base in node.bases:
            name = self._name(base)
            if name:
                self.edges.append(Edge(node_id, name, "inherits"))
        self.class_stack.append(node.name)
        self.scope_stack.append(node_id)
        self.generic_visit(node)
        self.scope_stack.pop()
        self.class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = self._name(node.func)
        if name:
            self.edges.append(Edge(self.scope_stack[-1], name, "calls"))
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        self.edges.append(Edge(self.scope_stack[-1], node.id, "references"))

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if self.class_stack:
            node_id = f"{self.rel}:{self.class_stack[-1]}.{node.name}"
            node_type = "method"
        else:
            node_id = f"{self.rel}:{node.name}"
            node_type = "function"
        self.nodes.append(Node(node_id, node_type, self.rel))
        self.edges.append(Edge(self.scope_stack[-1], node_id, "defines"))
        self.scope_stack.append(node_id)
        self.generic_visit(node)
        self.scope_stack.pop()

    def _name(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            base = self._name(node.value)
            return f"{base}.{node.attr}" if base else node.attr
        return ""

