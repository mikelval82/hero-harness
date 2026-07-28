## Code graph

The codebase dependency graph is available through the read-only `CodeGraph`
tool. Use it first for structural relationships, then confirm relevant details
with `Read`, `Glob`, or `Grep`.

| Action | Required input | Purpose |
|---|---|---|
| `find_nodes` | `pattern` | Find node ids by literal, case-insensitive substring |
| `dependencies` | `node` | Direct callees/dependencies of an exact node id |
| `dependents` | `node` | Direct callers/dependents of an exact node id |
| `impact_analysis` | `node` | Transitive callers affected by changing an exact node id |
| `dead_code` | none | Non-module nodes with zero dependency callers |

You may set `limit` from 1 to 200; the default and hard maximum are 200. Do
not provide shell commands, SQL, database paths, interpreters, or a `build`
action. Node ids use `filepath:name` for functions, `filepath:Class.method` for
methods, and `filepath` for modules.

The runtime builds the graph before task work and rebuilds it immediately
before every REVIEW, including re-reviews. If the graph is unavailable or the
requested node is absent, treat the error as recoverable and continue with
`Read`, `Glob`, and `Grep`.

The graph currently covers static Python structure. Dynamic wiring,
reflection, plugins, runtime dispatch, and other languages may be incomplete;
graph output is supporting evidence, not the sole source of truth.
