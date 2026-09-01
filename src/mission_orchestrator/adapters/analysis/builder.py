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
    name: str


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    relation: str


STRUCTURAL_RELATIONS = {"defines", "imports", "inherits"}


class CodeGraphBuilder:
    def __init__(self, graph: SQLiteCodeGraph) -> None:
        self.graph = graph

    def build(self, root_dir: Path, *, force: bool = False) -> None:
        root = root_dir.resolve()
        files = self._discover_python_files(root)
        present = {path.relative_to(root).as_posix() for path in files}
        changed = False
        with self.graph.session() as connection:
            known = [row[0] for row in connection.execute("SELECT path FROM files")]
            for rel in known:
                if rel not in present:
                    self._purge_file(connection, rel)
                    changed = True
            for path in files:
                rel = path.relative_to(root).as_posix()
                try:
                    mtime = path.stat().st_mtime_ns
                except OSError:
                    continue
                current = connection.execute(
                    "SELECT mtime_ns FROM files WHERE path = ?", (rel,)
                ).fetchone()
                if current and int(current[0]) == mtime and not force:
                    continue
                self._purge_file(connection, rel)
                nodes, edges, refs = self._parse_file(path, rel)
                connection.executemany(
                    "INSERT OR REPLACE INTO nodes(id, type, file, name) VALUES (?, ?, ?, ?)",
                    [(node.id, node.type, node.file, node.name) for node in nodes],
                )
                connection.executemany(
                    "INSERT OR IGNORE INTO edges(source, target, relation, file) VALUES (?, ?, ?, ?)",
                    [(edge.source, edge.target, edge.relation, rel) for edge in edges],
                )
                connection.executemany(
                    "INSERT OR IGNORE INTO lexical_refs(source, target, relation, file) VALUES (?, ?, ?, ?)",
                    [(ref.source, ref.target, ref.relation, rel) for ref in refs],
                )
                connection.execute(
                    "INSERT OR REPLACE INTO files(path, mtime_ns) VALUES (?, ?)",
                    (rel, mtime),
                )
                changed = True
            if changed:
                self.graph.rebuild_fts(connection)
                self.graph.bump_observed_revision(connection)

    @staticmethod
    def _purge_file(connection, rel: str) -> None:
        connection.execute("DELETE FROM edges WHERE file = ?", (rel,))
        connection.execute("DELETE FROM lexical_refs WHERE file = ?", (rel,))
        connection.execute("DELETE FROM nodes WHERE file = ?", (rel,))
        connection.execute("DELETE FROM files WHERE path = ?", (rel,))

    def _discover_python_files(self, root: Path) -> list[Path]:
        try:
            result = subprocess.run(
                ["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.py"],
                cwd=root,
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
        except Exception:
            result = None
        if result and result.returncode == 0 and result.stdout.strip():
            paths = [root / line for line in result.stdout.splitlines() if line.strip()]
            return [path for path in paths if path.exists()]
        return [path for path in root.rglob("*.py") if ".venv" not in path.parts and ".git" not in path.parts]

    def _parse_file(self, path: Path, rel: str) -> tuple[list[Node], list[Edge], list[Edge]]:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            return [Node(rel, "module", rel, rel)], [], []
        nodes = [Node(rel, "module", rel, rel)]
        edges: list[Edge] = []
        refs: list[Edge] = []
        visitor = _GraphVisitor(rel, nodes, edges, refs)
        visitor.visit(tree)
        return nodes, edges, refs


class _GraphVisitor(ast.NodeVisitor):
    def __init__(self, rel: str, nodes: list[Node], edges: list[Edge], refs: list[Edge]) -> None:
        self.rel = rel
        self.nodes = nodes
        self.edges = edges
        self.refs = refs
        self.qual_stack: list[str] = []
        self.kind_stack: list[str] = []
        self.scope_stack: list[str] = [rel]

    def _qualified_id(self, name: str) -> str:
        qualname = ".".join([*self.qual_stack, name])
        return f"{self.rel}:{qualname}"

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.edges.append(Edge(self.scope_stack[-1], alias.name, "imports"))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = "." * node.level + (node.module or "")
        self.edges.append(Edge(self.scope_stack[-1], module, "imports"))

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        node_id = self._qualified_id(node.name)
        self.nodes.append(Node(node_id, "class", self.rel, node.name))
        self.edges.append(Edge(self.scope_stack[-1], node_id, "defines"))
        for base in node.bases:
            name = self._name(base)
            if name:
                self.edges.append(Edge(node_id, name, "inherits"))
        self.qual_stack.append(node.name)
        self.kind_stack.append("class")
        self.scope_stack.append(node_id)
        self.generic_visit(node)
        self.scope_stack.pop()
        self.kind_stack.pop()
        self.qual_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = self._name(node.func)
        if name:
            self.refs.append(Edge(self.scope_stack[-1], name, "calls"))
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        self.refs.append(Edge(self.scope_stack[-1], node.id, "references"))

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        node_id = self._qualified_id(node.name)
        node_type = "method" if self.kind_stack and self.kind_stack[-1] == "class" else "function"
        self.nodes.append(Node(node_id, node_type, self.rel, node.name))
        self.edges.append(Edge(self.scope_stack[-1], node_id, "defines"))
        self.qual_stack.append(node.name)
        self.kind_stack.append("function")
        self.scope_stack.append(node_id)
        self.generic_visit(node)
        self.scope_stack.pop()
        self.kind_stack.pop()
        self.qual_stack.pop()

    def _name(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            base = self._name(node.value)
            return f"{base}.{node.attr}" if base else node.attr
        return ""

