#!/usr/bin/env python3
import argparse
import sqlite3
import sys

from src.analysis.builder import (
    build_graph,
    discover_files,
    parse_file,
    parse_file_ts,
)
from src.analysis.code_graph_queries import (
    MAX_CODE_GRAPH_ROWS,
    open_graph_read_only,
    query_graph,
)
from src.analysis.sqlite_graph import SqliteGraph
from src.core.paths import HARNESS


def cmd_build(args):
    force = getattr(args, "force", False)
    db_path = HARNESS / "code_graph.db"
    invalid_marker = db_path.with_suffix(".invalid")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    invalid_marker.write_text("rebuild pending or failed\n", encoding="utf-8")

    graph = None
    if not force and db_path.exists():
        try:
            graph = SqliteGraph()
            file_conn = sqlite3.connect(str(db_path))
            file_conn.backup(graph._conn)
            file_conn.close()
            graph = build_graph(args.root_dir, G=graph)
        except Exception:
            graph = build_graph(args.root_dir)
    else:
        graph = build_graph(args.root_dir)

    graph.commit()
    if db_path.exists():
        db_path.unlink()
    dest = sqlite3.connect(str(db_path))
    graph._conn.backup(dest)
    dest.close()
    invalid_marker.unlink()
    print(
        f"Built graph: {graph.number_of_nodes()} nodes, "
        f"{graph.number_of_edges()} edges ({db_path})"
    )


def _load_graph():
    try:
        return open_graph_read_only(HARNESS / "code_graph.db")
    except (FileNotFoundError, sqlite3.Error, OSError) as exc:
        print(f"code_graph.db not available: {exc}", file=sys.stderr)
        sys.exit(1)


def _run_query(inp: dict) -> tuple[list[str], list[tuple]]:
    try:
        with _load_graph() as connection:
            return query_graph(connection, inp)
    except (ValueError, sqlite3.Error, OSError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)


def cmd_dependencies(args):
    _, rows = _run_query({
        "action": "dependencies",
        "node": args.node,
        "limit": getattr(args, "limit", MAX_CODE_GRAPH_ROWS),
    })
    for relation, _type, node_id, _file in rows:
        print(f"{relation}\t{node_id}")


def cmd_dependents(args):
    _, rows = _run_query({
        "action": "dependents",
        "node": args.node,
        "limit": getattr(args, "limit", MAX_CODE_GRAPH_ROWS),
    })
    for relation, _type, node_id, _file in rows:
        print(f"{relation}\t{node_id}")


def cmd_impact_analysis(args):
    _, rows = _run_query({
        "action": "impact_analysis",
        "node": args.node,
        "limit": getattr(args, "limit", MAX_CODE_GRAPH_ROWS),
    })
    for _type, node_id, _file in rows:
        print(node_id)


def cmd_find_node(args):
    _, rows = _run_query({
        "action": "find_nodes",
        "pattern": args.pattern,
        "limit": getattr(args, "limit", MAX_CODE_GRAPH_ROWS),
    })
    for type_, node_id, _file in rows:
        print(f"{type_}\t{node_id}")


def cmd_dead_code(args):
    _, rows = _run_query({
        "action": "dead_code",
        "limit": getattr(args, "limit", MAX_CODE_GRAPH_ROWS),
    })
    for type_, node_id, _file in rows:
        print(f"{type_}\t{node_id}")


def _add_limit(parser):
    parser.add_argument(
        "--limit",
        type=int,
        default=MAX_CODE_GRAPH_ROWS,
        help=f"Maximum rows (1-{MAX_CODE_GRAPH_ROWS})",
    )


def main():
    parser = argparse.ArgumentParser(description="Code dependency graph tool")
    subs = parser.add_subparsers(dest="command")

    p_build = subs.add_parser("build", help="Build the dependency graph")
    p_build.add_argument("root_dir", help="Root directory of the Python project")
    p_build.add_argument(
        "--force", action="store_true",
        help="Force full rebuild, ignore existing database",
    )
    p_build.set_defaults(func=cmd_build)

    p_deps = subs.add_parser("dependencies", help="List what a node depends on")
    p_deps.add_argument("node", help="Node ID (e.g. scripts/foo.py:func_name)")
    _add_limit(p_deps)
    p_deps.set_defaults(func=cmd_dependencies)

    p_dents = subs.add_parser("dependents", help="List what depends on a node")
    p_dents.add_argument("node", help="Node ID")
    _add_limit(p_dents)
    p_dents.set_defaults(func=cmd_dependents)

    p_impact = subs.add_parser(
        "impact-analysis", help="Transitive closure of dependents",
    )
    p_impact.add_argument("node", help="Node ID")
    _add_limit(p_impact)
    p_impact.set_defaults(func=cmd_impact_analysis)

    p_find = subs.add_parser(
        "find-node", help="Find nodes by substring (case-insensitive)",
    )
    p_find.add_argument("pattern", help="Search pattern")
    _add_limit(p_find)
    p_find.set_defaults(func=cmd_find_node)

    p_dead = subs.add_parser("dead-code", help="List nodes with zero callers")
    _add_limit(p_dead)
    p_dead.set_defaults(func=cmd_dead_code)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
