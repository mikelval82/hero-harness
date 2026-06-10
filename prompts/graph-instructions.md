## Code graph

A dependency graph of the codebase is available via CLI. Use it to understand call relationships before modifying code.

**Invocation:** `python3 src/analysis/code_graph.py <command> [args]`

**Commands:**

| Command | Description |
|---|---|
| `dependencies <node>` | What this node calls (direct callees) |
| `dependents <node>` | Who calls this node (direct callers) |
| `impact-analysis <node>` | Transitive impact — all nodes affected by a change |
| `find-node <pattern>` | Search nodes by substring pattern |
| `dead-code` | Nodes with zero callers (potential unused code) |

**Node ID format:** `filepath:name` (functions), `filepath:Class.method` (methods), `filepath` (modules).

**Note:** The graph (`code_graph.db`) is built automatically after the structure phase and rebuilt incrementally before each task. If the build failed (e.g., syntax errors in source files), the graph may not exist and query commands will return an error — this is expected, proceed without it.
