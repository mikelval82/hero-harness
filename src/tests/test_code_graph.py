import sys
import io
import ast
import subprocess
from pathlib import Path
from contextlib import redirect_stdout
from argparse import Namespace

import sqlite3

from src.analysis import code_graph
import pytest


def _capture(fn, *args):
    buf = io.StringIO()
    with redirect_stdout(buf):
        fn(*args)
    return buf.getvalue()


def _patch_git(monkeypatch):
    monkeypatch.setattr(subprocess, "run",
        lambda *a, **kw: subprocess.CompletedProcess(a[0], 1))


@pytest.fixture
def graph_project(tmp_path, monkeypatch):
    _patch_git(monkeypatch)
    (tmp_path / "mod_a.py").write_text(
        "import mod_b\n"
        "def caller(): mod_b.helper()\n"
        "class Base: pass\n"
    )
    (tmp_path / "mod_b.py").write_text(
        "from mod_a import Base\n"
        "def helper(): pass\n"
        "class Child(Base):\n"
        "    def method(self): self.other()\n"
        "    def other(self): pass\n"
    )
    return tmp_path


@pytest.fixture
def graph_db(graph_project, monkeypatch):
    root = graph_project
    G = code_graph.build_graph(str(root))
    G.commit()
    db_path = root / "code_graph.db"
    dest = sqlite3.connect(str(db_path))
    G._conn.backup(dest)
    dest.close()
    monkeypatch.setattr(code_graph, "HARNESS", root)
    return root, G


# --- discover_files ---

def test_discover_files_rglob_fallback(tmp_path, monkeypatch):
    _patch_git(monkeypatch)
    (tmp_path / "a.py").write_text("pass")
    (tmp_path / "b.py").write_text("pass")
    result = code_graph.discover_files(str(tmp_path))
    assert set(result) == {"a.py", "b.py"}


# --- parse_file ---

def test_parse_file_valid(tmp_path):
    (tmp_path / "ok.py").write_text("x = 1")
    tree = code_graph.parse_file("ok.py", str(tmp_path))
    assert isinstance(tree, ast.Module)


def test_parse_file_syntax_error(tmp_path):
    (tmp_path / "bad.py").write_text("def !!!")
    result = code_graph.parse_file("bad.py", str(tmp_path))
    assert result is None


# --- build_graph ---

def test_build_graph_nodes(graph_project):
    G = code_graph.build_graph(str(graph_project))
    assert G.number_of_nodes() == 8
    expected = {
        "mod_a.py": "module",
        "mod_b.py": "module",
        "mod_a.py:caller": "function",
        "mod_a.py:Base": "class",
        "mod_b.py:helper": "function",
        "mod_b.py:Child": "class",
        "mod_b.py:Child.method": "method",
        "mod_b.py:Child.other": "method",
    }
    for node_id, node_type in expected.items():
        assert G.nodes[node_id]["type"] == node_type


def test_build_graph_edges(graph_project):
    G = code_graph.build_graph(str(graph_project))
    expected_dep = [
        ("mod_a.py", "mod_b.py", "imports"),
        ("mod_b.py", "mod_a.py", "imports"),
        ("mod_a.py:caller", "mod_b.py:helper", "calls"),
        ("mod_b.py:Child", "mod_a.py:Base", "inherits"),
        ("mod_b.py:Child.method", "mod_b.py:Child.other", "calls"),
    ]
    expected_defines = [
        ("mod_a.py", "mod_a.py:caller"),
        ("mod_a.py", "mod_a.py:Base"),
        ("mod_b.py", "mod_b.py:helper"),
        ("mod_b.py", "mod_b.py:Child"),
        ("mod_b.py:Child", "mod_b.py:Child.method"),
        ("mod_b.py:Child", "mod_b.py:Child.other"),
    ]
    for src, tgt, rel in expected_dep:
        assert G.has_edge(src, tgt), f"Missing edge: {src} -> {tgt}"
        assert G.edges[src, tgt]["relation"] == rel
    for src, tgt in expected_defines:
        assert G.has_edge(src, tgt), f"Missing defines edge: {src} -> {tgt}"
        assert G.edges[src, tgt]["relation"] == "defines"
    assert G.number_of_edges() == len(expected_dep) + len(expected_defines)


def test_build_graph_no_self_recursion(tmp_path, monkeypatch):
    _patch_git(monkeypatch)
    (tmp_path / "rec.py").write_text("def recurse(): recurse()\n")
    G = code_graph.build_graph(str(tmp_path))
    assert ("rec.py:recurse", "rec.py:recurse") not in G.edges


def test_build_graph_empty_project(tmp_path, monkeypatch):
    _patch_git(monkeypatch)
    G = code_graph.build_graph(str(tmp_path))
    assert G.number_of_nodes() == 0
    assert G.number_of_edges() == 0


def test_build_graph_skips_syntax_error(tmp_path, monkeypatch):
    _patch_git(monkeypatch)
    (tmp_path / "good.py").write_text("def ok(): pass\n")
    (tmp_path / "bad.py").write_text("def !!!\n")
    G = code_graph.build_graph(str(tmp_path))
    assert G.has_node("good.py:ok")
    # tree-sitter is error-tolerant: bad.py gets a module node but no functions
    assert G.has_node("bad.py")
    assert G.nodes["bad.py"]["type"] == "module"
    bad_nodes = [n for n in G.nodes if n.startswith("bad.py:")]
    assert bad_nodes == []


def test_build_graph_partial_syntax_error(tmp_path, monkeypatch):
    _patch_git(monkeypatch)
    (tmp_path / "mixed.py").write_text(
        "def ok(): pass\n"
        "def !!!\n"
        "class Good: pass\n"
    )
    G = code_graph.build_graph(str(tmp_path))
    assert G.has_node("mixed.py")
    assert G.has_node("mixed.py:ok")
    assert G.has_node("mixed.py:Good")
    mixed_nodes = [n for n in G.nodes if n.startswith("mixed.py:")]
    assert set(mixed_nodes) == {"mixed.py:ok", "mixed.py:Good"}


def test_build_graph_relative_import_skipped(tmp_path, monkeypatch):
    _patch_git(monkeypatch)
    (tmp_path / "rel.py").write_text("from . import something\ndef foo(): pass\n")
    G = code_graph.build_graph(str(tmp_path))
    assert G.has_node("rel.py")
    assert G.has_node("rel.py:foo")
    assert G.has_edge("rel.py", "rel.py:foo")
    assert G.edges["rel.py", "rel.py:foo"]["relation"] == "defines"
    dep_edges = G._conn.execute(
        "SELECT COUNT(*) FROM edges WHERE relation != 'defines'"
    ).fetchone()[0]
    assert dep_edges == 0


# --- cmd_build ---

def test_cmd_build(graph_project, monkeypatch):
    monkeypatch.setattr(code_graph, "HARNESS", graph_project)
    out = _capture(code_graph.cmd_build, Namespace(root_dir=str(graph_project)))
    db_path = graph_project / "code_graph.db"
    assert db_path.exists()
    conn = sqlite3.connect(str(db_path))
    try:
        node_count = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        edge_count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        assert node_count > 0
        assert edge_count > 0
    finally:
        conn.close()
    assert "nodes" in out
    assert "edges" in out


# --- _load_graph ---

def test_load_graph_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(code_graph, "HARNESS", tmp_path)
    with pytest.raises(SystemExit):
        code_graph._load_graph()


# --- cmd_dependencies ---

def test_cmd_dependencies_happy(graph_db):
    root, G = graph_db
    out = _capture(code_graph.cmd_dependencies, Namespace(node="mod_a.py:caller"))
    assert "calls\tmod_b.py:helper" in out


def test_cmd_dependencies_unknown_node(graph_db):
    with pytest.raises(SystemExit):
        code_graph.cmd_dependencies(Namespace(node="nonexistent"))


# --- cmd_dependents ---

def test_cmd_dependents_happy(graph_db):
    root, G = graph_db
    out = _capture(code_graph.cmd_dependents, Namespace(node="mod_b.py:helper"))
    assert "calls\tmod_a.py:caller" in out


def test_cmd_dependents_unknown_node(graph_db):
    with pytest.raises(SystemExit):
        code_graph.cmd_dependents(Namespace(node="nonexistent"))


# --- cmd_impact_analysis ---

def test_cmd_impact_analysis_happy(graph_db):
    root, G = graph_db
    out = _capture(code_graph.cmd_impact_analysis, Namespace(node="mod_b.py:helper"))
    assert "mod_a.py:caller" in out


def test_cmd_impact_analysis_unknown_node(graph_db):
    with pytest.raises(SystemExit):
        code_graph.cmd_impact_analysis(Namespace(node="nonexistent"))


# --- cmd_find_node ---

def test_cmd_find_node(graph_db):
    root, G = graph_db
    out = _capture(code_graph.cmd_find_node, Namespace(pattern="helper"))
    assert "function\tmod_b.py:helper" in out


def test_cmd_find_node_case_insensitive(graph_db):
    root, G = graph_db
    out = _capture(code_graph.cmd_find_node, Namespace(pattern="CHILD"))
    items = {line.split("\t")[1] for line in out.strip().splitlines()}
    assert "mod_b.py:Child" in items
    assert "mod_b.py:Child.method" in items
    assert "mod_b.py:Child.other" in items


# --- cmd_dead_code ---

def test_cmd_dead_code(graph_db):
    root, G = graph_db
    out = _capture(code_graph.cmd_dead_code, Namespace())
    lines = out.strip().splitlines()
    assert len(lines) == 3
    items = {line.split("\t")[1] for line in lines}
    assert items == {"mod_a.py:caller", "mod_b.py:Child", "mod_b.py:Child.method"}
    assert "mod_a.py:Base" not in out


# --- incremental sync ---


def test_incremental_noop(graph_project):
    G = code_graph.build_graph(str(graph_project))
    G.commit()
    initial_nodes = G.number_of_nodes()
    initial_edges = G.number_of_edges()
    initial_files = G.get_files()
    G2 = code_graph.build_graph(str(graph_project), G=G)
    assert G2 is G
    assert G2.number_of_nodes() == initial_nodes
    assert G2.number_of_edges() == initial_edges
    assert G2.get_files() == initial_files


def test_incremental_mtime_change(graph_project):
    G = code_graph.build_graph(str(graph_project))
    G.commit()
    assert G.number_of_nodes() == 8
    assert G.has_node("mod_b.py:helper")
    (graph_project / "mod_b.py").write_text(
        "from mod_a import Base\n"
        "def helper(): pass\n"
        "class Child(Base):\n"
        "    def method(self): self.other()\n"
        "    def other(self): pass\n"
        "def new_func(): pass\n"
    )
    G2 = code_graph.build_graph(str(graph_project), G=G)
    assert G2.has_node("mod_b.py:new_func")
    assert G2.has_node("mod_b.py:helper")
    assert G2.has_node("mod_a.py:caller")
    assert G2.has_node("mod_a.py:Base")
    assert G2.number_of_nodes() == 9
    assert G2.has_edge("mod_b.py:Child", "mod_a.py:Base")
    files = G2.get_files()
    assert len(files) == 2
    assert "mod_b.py" in files
    assert "mod_a.py" in files


def test_incremental_deleted_file(graph_project):
    G = code_graph.build_graph(str(graph_project))
    G.commit()
    assert G.has_node("mod_b.py:helper")
    assert G.has_node("mod_b.py:Child")
    (graph_project / "mod_b.py").unlink()
    G2 = code_graph.build_graph(str(graph_project), G=G)
    assert not G2.has_node("mod_b.py")
    assert not G2.has_node("mod_b.py:helper")
    assert not G2.has_node("mod_b.py:Child")
    assert not G2.has_node("mod_b.py:Child.method")
    assert not G2.has_node("mod_b.py:Child.other")
    assert G2.has_node("mod_a.py")
    assert G2.has_node("mod_a.py:caller")
    assert G2.has_node("mod_a.py:Base")
    assert G2.number_of_nodes() == 3
    assert not G2.has_edge("mod_a.py", "mod_b.py")
    assert not G2.has_edge("mod_b.py", "mod_a.py")
    assert not G2.has_edge("mod_a.py:caller", "mod_b.py:helper")
    assert G2.has_edge("mod_a.py", "mod_a.py:caller")
    assert G2.has_edge("mod_a.py", "mod_a.py:Base")
    dep_edges = G2._conn.execute(
        "SELECT COUNT(*) FROM edges WHERE relation != 'defines'"
    ).fetchone()[0]
    assert dep_edges == 0
    files = G2.get_files()
    assert len(files) == 1
    assert "mod_a.py" in files
    assert "mod_b.py" not in files


def test_cmd_build_force(graph_project, monkeypatch):
    monkeypatch.setattr(code_graph, "HARNESS", graph_project)
    _capture(code_graph.cmd_build, Namespace(root_dir=str(graph_project)))
    assert (graph_project / "code_graph.db").exists()
    out = _capture(code_graph.cmd_build, Namespace(root_dir=str(graph_project), force=True))
    assert "nodes" in out
    assert "edges" in out
    conn = sqlite3.connect(str(graph_project / "code_graph.db"))
    try:
        node_count = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        edge_count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        file_count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        assert node_count == 8
        assert edge_count == 11
        assert file_count == 2
    finally:
        conn.close()
