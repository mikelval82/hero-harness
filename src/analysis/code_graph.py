#!/usr/bin/env python3
import sys
import argparse

import sqlite3

from src.analysis.sqlite_graph import SqliteGraph
from src.analysis.builder import (
    discover_files, parse_file, parse_file_ts, build_graph,
)
from src.core.paths import HARNESS


def cmd_build(args):
    force = getattr(args, 'force', False)
    db_path = HARNESS / "code_graph.db"

    G = None
    if not force and db_path.exists():
        try:
            G = SqliteGraph()
            file_conn = sqlite3.connect(str(db_path))
            file_conn.backup(G._conn)
            file_conn.close()
            G = build_graph(args.root_dir, G=G)
        except Exception:
            G = build_graph(args.root_dir)
    else:
        G = build_graph(args.root_dir)

    G.commit()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    dest = sqlite3.connect(str(db_path))
    G._conn.backup(dest)
    dest.close()
    print(f"Built graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges ({db_path})")


def _load_graph():
    path = HARNESS / "code_graph.db"
    if not path.exists():
        print("code_graph.db not found — run 'build' first", file=sys.stderr)
        sys.exit(1)
    return SqliteGraph(db_path=str(path))


def cmd_dependencies(args):
    G = _load_graph()
    if args.node not in G:
        print(f"Node not found: {args.node}", file=sys.stderr)
        sys.exit(1)
    for t in G.successors(args.node):
        print(f"{G.edges[args.node, t]['relation']}	{t}")


def cmd_dependents(args):
    G = _load_graph()
    if args.node not in G:
        print(f"Node not found: {args.node}", file=sys.stderr)
        sys.exit(1)
    for s in G.predecessors(args.node):
        print(f"{G.edges[s, args.node]['relation']}	{s}")


def cmd_impact_analysis(args):
    G = _load_graph()
    if args.node not in G:
        print(f"Node not found: {args.node}", file=sys.stderr)
        sys.exit(1)
    for n in sorted(G.ancestors(args.node)):
        print(n)


def cmd_find_node(args):
    G = _load_graph()
    pattern = args.pattern
    if len(pattern) >= 3:
        escaped = pattern.replace('"', '""')
        fts_pattern = f'"{escaped}"'
        rows = G._conn.execute(
            "SELECT n.type, n.id FROM nodes_fts f "
            "JOIN nodes n ON n.id = f.id "
            "WHERE nodes_fts MATCH ?",
            (fts_pattern,),
        ).fetchall()
    else:
        like_pattern = f"%{pattern}%"
        rows = G._conn.execute(
            "SELECT type, id FROM nodes WHERE LOWER(id) LIKE LOWER(?)",
            (like_pattern,),
        ).fetchall()
    for type_, node_id in rows:
        print(f"{type_}\t{node_id}")


def cmd_dead_code(args):
    G = _load_graph()
    dead = [n for n in G.nodes if G.in_degree_deps(n) == 0 and G.nodes[n]['type'] != 'module']
    for n in sorted(dead, key=lambda n: (G.nodes[n]['file'], n)):
        print(f"{G.nodes[n]['type']}	{n}")


def main():
    parser = argparse.ArgumentParser(description="Code dependency graph tool")
    subs = parser.add_subparsers(dest="command")

    p_build = subs.add_parser("build", help="Build the dependency graph")
    p_build.add_argument("root_dir", help="Root directory of the Python project")
    p_build.add_argument("--force", action="store_true", help="Force full rebuild, ignore existing database")
    p_build.set_defaults(func=cmd_build)

    p_deps = subs.add_parser("dependencies", help="List what a node depends on")
    p_deps.add_argument("node", help="Node ID (e.g. scripts/foo.py:func_name)")
    p_deps.set_defaults(func=cmd_dependencies)

    p_dents = subs.add_parser("dependents", help="List what depends on a node")
    p_dents.add_argument("node", help="Node ID")
    p_dents.set_defaults(func=cmd_dependents)

    p_impact = subs.add_parser("impact-analysis", help="Transitive closure of dependents")
    p_impact.add_argument("node", help="Node ID")
    p_impact.set_defaults(func=cmd_impact_analysis)

    p_find = subs.add_parser("find-node", help="Find nodes by substring (case-insensitive)")
    p_find.add_argument("pattern", help="Search pattern")
    p_find.set_defaults(func=cmd_find_node)

    p_dead = subs.add_parser("dead-code", help="List nodes with no incoming edges")
    p_dead.set_defaults(func=cmd_dead_code)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
