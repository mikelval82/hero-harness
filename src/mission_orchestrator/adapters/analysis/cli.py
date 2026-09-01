from __future__ import annotations

import argparse
from pathlib import Path

from mission_orchestrator.adapters.analysis.builder import CodeGraphBuilder
from mission_orchestrator.adapters.analysis.sqlite_graph import SQLiteCodeGraph


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="code-graph")
    parser.add_argument("--db", default="code_graph.db")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("root_dir")
    build.add_argument("--force", action="store_true")
    deps = sub.add_parser("dependencies")
    deps.add_argument("node")
    dents = sub.add_parser("dependents")
    dents.add_argument("node")
    impact = sub.add_parser("impact-analysis")
    impact.add_argument("node")
    find = sub.add_parser("find-node")
    find.add_argument("pattern")
    sub.add_parser("dead-code")
    args = parser.parse_args(argv)
    graph = SQLiteCodeGraph(Path(args.db))
    if args.command == "build":
        CodeGraphBuilder(graph).build(Path(args.root_dir), force=args.force)
        print(f"built {args.db}")
    elif args.command == "dependencies":
        for target, relation in graph.dependencies(args.node):
            print(f"{relation}: {target}")
    elif args.command == "dependents":
        for source, relation in graph.dependents(args.node):
            print(f"{relation}: {source}")
    elif args.command == "impact-analysis":
        seen = set()
        frontier = [args.node]
        while frontier:
            node = frontier.pop()
            for source, relation in graph.dependents(node):
                if source not in seen:
                    seen.add(source)
                    frontier.append(source)
                    print(f"{relation}: {source}")
    elif args.command == "find-node":
        for node_id, node_type, file in graph.find_node(args.pattern):
            print(f"{node_type}: {node_id} ({file})")
    elif args.command == "dead-code":
        for node in graph.dead_code():
            print(node)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

