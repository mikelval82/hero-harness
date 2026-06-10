import ast
import subprocess
import sys
from pathlib import Path

import tree_sitter
import tree_sitter_python

from src.analysis.sqlite_graph import SqliteGraph


_ts_parser = None
_ts_language = None


def _get_ts_parser():
    global _ts_parser, _ts_language
    if _ts_parser is None:
        _ts_language = tree_sitter.Language(tree_sitter_python.language())
        _ts_parser = tree_sitter.Parser(_ts_language)
    return _ts_parser


def discover_files(root):
    result = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        files = [l for l in result.stdout.splitlines() if l.strip()]
    else:
        files = [
            str(p.relative_to(root).as_posix())
            for p in Path(root).rglob("*.py")
        ]
    return files


def parse_file(filepath, root):
    try:
        source = Path(root, filepath).read_text(encoding="utf-8")
        return ast.parse(source, filename=filepath)
    except (SyntaxError, UnicodeDecodeError) as e:
        print(f"Warning: skipping {filepath}: {e}", file=sys.stderr)
        return None


def parse_file_ts(filepath, root):
    try:
        source_bytes = Path(root, filepath).read_bytes()
    except (OSError, UnicodeDecodeError) as e:
        print(f"Warning: skipping {filepath}: {e}", file=sys.stderr)
        return None
    parser = _get_ts_parser()
    return parser.parse(source_bytes)


def extract_nodes_ts(tree, rel_path, G):
    G.add_node(rel_path, type="module", file=rel_path)
    local_names = {}
    for child in tree.root_node.children:
        if child.type == "decorated_definition":
            child = child.child_by_field_name("definition")
        if child.type == "class_definition":
            class_name = child.child_by_field_name("name").text.decode()
            cls_id = f"{rel_path}:{class_name}"
            G.add_node(cls_id, type="class", file=rel_path)
            G.add_edge(rel_path, cls_id, relation="defines")
            local_names[class_name] = cls_id
            body = child.child_by_field_name("body")
            for body_child in body.children:
                if body_child.type == "decorated_definition":
                    body_child = body_child.child_by_field_name("definition")
                if body_child.type == "function_definition":
                    method_name = body_child.child_by_field_name("name").text.decode()
                    method_id = f"{rel_path}:{class_name}.{method_name}"
                    G.add_node(method_id, type="method", file=rel_path)
                    G.add_edge(cls_id, method_id, relation="defines")
        elif child.type == "function_definition":
            name = child.child_by_field_name("name").text.decode()
            func_id = f"{rel_path}:{name}"
            G.add_node(func_id, type="function", file=rel_path)
            G.add_edge(rel_path, func_id, relation="defines")
            local_names[name] = func_id
    return local_names


def _walk_ts(node):
    yield node
    for child in node.children:
        yield from _walk_ts(child)


def _resolve_module(name, known_modules):
    if name in known_modules:
        return known_modules[name]
    parts = name.split(".")
    for i in range(1, len(parts)):
        stripped = ".".join(parts[i:])
        if stripped in known_modules:
            return known_modules[stripped]
    return None


def extract_imports_ts(tree, rel_path, known_modules, G):
    import_names = {}
    for node in _walk_ts(tree.root_node):
        if node.type == "import_statement":
            for child in node.children_by_field_name("name"):
                if child.type == "dotted_name":
                    name_text = child.text.decode()
                    target = _resolve_module(name_text, known_modules)
                    if target:
                        G.add_edge(rel_path, target, relation="imports")
                        local = name_text.split(".")[-1]
                        import_names[local] = target
                elif child.type == "aliased_import":
                    name_node = child.child_by_field_name("name")
                    name_text = name_node.text.decode()
                    alias_node = child.child_by_field_name("alias")
                    local = alias_node.text.decode()
                    target = _resolve_module(name_text, known_modules)
                    if target:
                        G.add_edge(rel_path, target, relation="imports")
                        import_names[local] = target

        elif node.type == "import_from_statement":
            module_name = node.child_by_field_name("module_name")
            if module_name is None or module_name.type == "relative_import":
                continue
            mod_text = module_name.text.decode()
            target_mod = _resolve_module(mod_text, known_modules)
            if target_mod is None:
                continue
            G.add_edge(rel_path, target_mod, relation="imports")
            for child in node.children_by_field_name("name"):
                if child.type == "dotted_name":
                    imported = child.text.decode()
                    local = imported
                elif child.type == "aliased_import":
                    imported = child.child_by_field_name("name").text.decode()
                    local = child.child_by_field_name("alias").text.decode()
                else:
                    continue
                candidate = f"{target_mod}:{imported}"
                if G.has_node(candidate):
                    import_names[local] = candidate
                else:
                    import_names[local] = target_mod

    return import_names


def _process_calls_ts(G, func_node, caller_id, rel_path, names, containing_class=None):
    for node in _walk_ts(func_node):
        if node.type != "call":
            continue
        func = node.child_by_field_name("function")
        if func is None:
            continue
        target_id = None
        if func.type == "identifier":
            name = func.text.decode()
            if name in names:
                target_id = names[name]
        elif func.type == "attribute":
            obj_node = func.child_by_field_name("object")
            attr_node = func.child_by_field_name("attribute")
            if obj_node is None or attr_node is None:
                continue
            obj_name = obj_node.text.decode()
            attr = attr_node.text.decode()
            if obj_name == "self" and containing_class:
                candidate = f"{rel_path}:{containing_class}.{attr}"
                if G.has_node(candidate):
                    target_id = candidate
            elif obj_name in names:
                resolved = names[obj_name]
                if G.has_node(resolved):
                    node_type = G.nodes[resolved].get("type")
                    if node_type == "module":
                        candidate = f"{resolved}:{attr}"
                    elif node_type == "class":
                        candidate = f"{resolved}.{attr}"
                    else:
                        candidate = None
                    if candidate and G.has_node(candidate):
                        target_id = candidate
        if target_id and G.has_node(target_id) and target_id != caller_id:
            G.add_edge(caller_id, target_id, relation="calls")
        args = node.child_by_field_name("arguments")
        if args:
            for arg in args.children:
                ref_node = None
                if arg.type == "identifier":
                    ref_node = arg
                elif arg.type == "keyword_argument":
                    value = arg.child_by_field_name("value")
                    if value and value.type == "identifier":
                        ref_node = value
                if ref_node is None:
                    continue
                ref_name = ref_node.text.decode()
                if ref_name in names:
                    ref_target = names[ref_name]
                    if G.has_node(ref_target) and ref_target != caller_id:
                        ref_type = G.nodes[ref_target].get("type")
                        if ref_type in ("function", "method", "class"):
                            G.add_edge(caller_id, ref_target, relation="references")


def extract_edges_ts(tree, rel_path, names, G):
    for child in tree.root_node.children:
        node = child
        if node.type == "decorated_definition":
            node = node.child_by_field_name("definition")
        if node.type == "class_definition":
            class_name = node.child_by_field_name("name").text.decode()
            child_id = f"{rel_path}:{class_name}"
            superclasses = node.child_by_field_name("superclasses")
            if superclasses is not None:
                for c in superclasses.children:
                    if c.type == "identifier":
                        base_name = c.text.decode()
                    elif c.type == "attribute":
                        base_name = f"{c.child_by_field_name('object').text.decode()}.{c.child_by_field_name('attribute').text.decode()}"
                    else:
                        continue
                    if base_name in names:
                        target = names[base_name]
                        if G.has_node(target) and G.nodes[target].get("type") == "class":
                            G.add_edge(child_id, target, relation="inherits")

    for child in tree.root_node.children:
        node = child
        if node.type == "decorated_definition":
            node = node.child_by_field_name("definition")
        if node.type == "function_definition":
            caller_id = f"{rel_path}:{node.child_by_field_name('name').text.decode()}"
            _process_calls_ts(G, node, caller_id, rel_path, names)
        elif node.type == "class_definition":
            class_name = node.child_by_field_name("name").text.decode()
            body = node.child_by_field_name("body")
            for body_child in body.children:
                method_node = body_child
                if method_node.type == "decorated_definition":
                    method_node = method_node.child_by_field_name("definition")
                if method_node.type == "function_definition":
                    method_name = method_node.child_by_field_name("name").text.decode()
                    caller_id = f"{rel_path}:{class_name}.{method_name}"
                    _process_calls_ts(G, method_node, caller_id, rel_path, names, containing_class=class_name)


def build_graph(root, G=None):
    incremental = G is not None
    if not incremental:
        G = SqliteGraph()

    files = discover_files(root)

    if incremental:
        stored = G.get_files()
        current_set = set()
        new_files = []
        modified_files = []

        for f in files:
            try:
                mtime_ns = Path(root, f).stat().st_mtime_ns
            except OSError:
                continue
            current_set.add(f)
            if f not in stored:
                new_files.append((f, mtime_ns))
            elif mtime_ns != stored[f]:
                modified_files.append((f, mtime_ns))

        deleted_files = [p for p in stored if p not in current_set]

        if not new_files and not modified_files and not deleted_files:
            return G

        stale_files = [f for f, _ in modified_files] + deleted_files
        for sf in stale_files:
            G.remove_nodes_by_file(sf)
            G.remove_file(sf)

        changed_files = new_files + modified_files
        trees = {}
        for f, mtime_ns in changed_files:
            tree = parse_file_ts(f, root)
            if tree is not None:
                trees[f] = tree
            G.add_file(f, mtime_ns)
    else:
        trees = {}
        for f in files:
            try:
                mtime_ns = Path(root, f).stat().st_mtime_ns
            except OSError:
                continue
            G.add_file(f, mtime_ns)
            tree = parse_file_ts(f, root)
            if tree is not None:
                trees[f] = tree

        known_modules = {}

    scope_map = {}

    for rel_path, tree in trees.items():
        scope_map[rel_path] = extract_nodes_ts(tree, rel_path, G)

        if not incremental:
            dotted = rel_path.replace("/", ".").replace("\\", ".")
            if dotted.endswith(".py"):
                dotted = dotted[:-3]
            known_modules[dotted] = rel_path

    if incremental:
        known_modules = {}
        for row in G._conn.execute("SELECT id, file FROM nodes WHERE type = 'module'").fetchall():
            module_id, file_path = row
            dotted = file_path.replace("/", ".").replace("\\", ".")
            if dotted.endswith(".py"):
                dotted = dotted[:-3]
            known_modules[dotted] = file_path

    import_names = {}

    for rel_path, tree in trees.items():
        import_names[rel_path] = extract_imports_ts(tree, rel_path, known_modules, G)

    for rel_path, tree in trees.items():
        names = dict(scope_map[rel_path])
        names.update(import_names[rel_path])
        extract_edges_ts(tree, rel_path, names, G)

    if incremental:
        G.cleanup_orphan_edges()

    return G
