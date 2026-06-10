import sqlite3


class _NodeView:
    def __init__(self, conn):
        self._conn = conn

    def __iter__(self):
        cur = self._conn.execute("SELECT id FROM nodes ORDER BY rowid")
        for row in cur:
            yield row[0]

    def __getitem__(self, node_id):
        row = self._conn.execute(
            "SELECT type, file FROM nodes WHERE id = ?", (node_id,)
        ).fetchone()
        if row is None:
            raise KeyError(node_id)
        return {"type": row[0], "file": row[1]}

    def __contains__(self, node_id):
        return self._conn.execute(
            "SELECT 1 FROM nodes WHERE id = ? LIMIT 1", (node_id,)
        ).fetchone() is not None


class _EdgeView:
    def __init__(self, conn):
        self._conn = conn

    def __contains__(self, key):
        source, target = key
        return self._conn.execute(
            "SELECT 1 FROM edges WHERE source = ? AND target = ? LIMIT 1",
            (source, target),
        ).fetchone() is not None

    def __getitem__(self, key):
        source, target = key
        row = self._conn.execute(
            "SELECT relation FROM edges WHERE source = ? AND target = ?",
            (source, target),
        ).fetchone()
        if row is None:
            raise KeyError(key)
        return {"relation": row[0]}


class SqliteGraph:
    """Directed graph backed by an in-memory SQLite database.

    Usage:
        G = SqliteGraph()
        G.add_node("mod.py", type="module", file="mod.py")
        G.add_node("mod.py:foo", type="function", file="mod.py")
        G.add_edge("mod.py:foo", "mod.py", relation="imports")
        assert G.has_node("mod.py")
        assert G.nodes["mod.py"]["type"] == "module"
    """

    def __init__(self, db_path=":memory:"):
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS nodes "
            "(id TEXT PRIMARY KEY, type TEXT NOT NULL, file TEXT NOT NULL)"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS edges "
            "(source TEXT NOT NULL, target TEXT NOT NULL, relation TEXT NOT NULL, "
            "PRIMARY KEY (source, target), "
            "FOREIGN KEY (source) REFERENCES nodes(id), "
            "FOREIGN KEY (target) REFERENCES nodes(id))"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS files "
            "(path TEXT PRIMARY KEY, mtime_ns INTEGER NOT NULL)"
        )
        self._conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts "
            "USING fts5(id, tokenize='trigram case_sensitive 0')"
        )
        self._conn.commit()
        self.nodes = _NodeView(self._conn)
        self.edges = _EdgeView(self._conn)

    def add_node(self, node_id, *, type, file):
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO nodes (id, type, file) VALUES (?, ?, ?)",
            (node_id, type, file),
        )
        if cur.rowcount > 0:
            self._conn.execute(
                "INSERT INTO nodes_fts(id) VALUES (?)",
                (node_id,),
            )

    def add_edge(self, source, target, *, relation):
        self._conn.execute(
            "INSERT OR REPLACE INTO edges (source, target, relation) VALUES (?, ?, ?)",
            (source, target, relation),
        )

    def add_file(self, path, mtime_ns):
        self._conn.execute(
            "INSERT OR REPLACE INTO files (path, mtime_ns) VALUES (?, ?)",
            (path, mtime_ns),
        )

    def get_files(self):
        return dict(self._conn.execute("SELECT path, mtime_ns FROM files").fetchall())

    def remove_nodes_by_file(self, file_path):
        rows = self._conn.execute("SELECT id FROM nodes WHERE file = ?", (file_path,)).fetchall()
        node_ids = [r[0] for r in rows]
        if not node_ids:
            return node_ids
        placeholders = ",".join("?" * len(node_ids))
        self._conn.execute("DELETE FROM nodes WHERE file = ?", (file_path,))
        self._conn.execute(f"DELETE FROM nodes_fts WHERE id IN ({placeholders})", node_ids)
        self._conn.execute(
            f"DELETE FROM edges WHERE source IN ({placeholders}) OR target IN ({placeholders})",
            node_ids + node_ids,
        )
        return node_ids

    def remove_file(self, file_path):
        self._conn.execute("DELETE FROM files WHERE path = ?", (file_path,))

    def cleanup_orphan_edges(self):
        self._conn.execute("DELETE FROM edges WHERE target NOT IN (SELECT id FROM nodes)")

    def has_node(self, node_id):
        return self._conn.execute(
            "SELECT 1 FROM nodes WHERE id = ? LIMIT 1", (node_id,)
        ).fetchone() is not None

    def has_edge(self, source, target):
        return self._conn.execute(
            "SELECT 1 FROM edges WHERE source = ? AND target = ? LIMIT 1",
            (source, target),
        ).fetchone() is not None

    def __contains__(self, node_id):
        return self.has_node(node_id)

    def successors(self, node_id):
        return [
            row[0]
            for row in self._conn.execute(
                "SELECT target FROM edges WHERE source = ?", (node_id,)
            ).fetchall()
        ]

    def predecessors(self, node_id):
        return [
            row[0]
            for row in self._conn.execute(
                "SELECT source FROM edges WHERE target = ?", (node_id,)
            ).fetchall()
        ]

    def in_degree(self, node_id):
        return self._conn.execute(
            "SELECT COUNT(*) FROM edges WHERE target = ?", (node_id,)
        ).fetchone()[0]

    def in_degree_deps(self, node_id):
        return self._conn.execute(
            "SELECT COUNT(*) FROM edges WHERE target = ? AND relation != 'defines'",
            (node_id,),
        ).fetchone()[0]

    def number_of_nodes(self):
        return self._conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]

    def number_of_edges(self):
        return self._conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]

    def ancestors(self, node_id):
        result = {
            row[0]
            for row in self._conn.execute(
                "WITH RECURSIVE anc(id) AS ("
                "  SELECT source FROM edges WHERE target = ? "
                "  UNION "
                "  SELECT e.source FROM edges e JOIN anc a ON e.target = a.id"
                ") SELECT id FROM anc",
                (node_id,),
            ).fetchall()
        }
        result.discard(node_id)
        return result

    def commit(self):
        self._conn.commit()
