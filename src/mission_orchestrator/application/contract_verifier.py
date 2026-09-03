from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ContractCheckState(Enum):
    PASSED = "passed"
    FAILED = "failed"
    ADVISORY = "advisory"


@dataclass(frozen=True)
class ContractCheck:
    node_id: str
    field: str
    state: ContractCheckState
    detail: str


@dataclass(frozen=True)
class ContractVerification:
    snapshot_id: str
    task_id: str
    checks: tuple[ContractCheck, ...]

    @property
    def passed(self) -> bool:
        return not any(check.state is ContractCheckState.FAILED for check in self.checks)

    def to_json(self) -> str:
        return json.dumps(
            {
                "snapshot_id": self.snapshot_id,
                "task_id": self.task_id,
                "passed": self.passed,
                "checks": [
                    {
                        "node_id": check.node_id,
                        "field": check.field,
                        "state": check.state.value,
                        "detail": check.detail,
                    }
                    for check in self.checks
                ],
            },
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )


@dataclass(frozen=True)
class _Symbol:
    kind: str
    node: ast.AST


@dataclass(frozen=True)
class _Parameter:
    name: str
    kind: str
    annotation: ast.expr | None
    has_default: bool


class PythonContractVerifier:
    """Checks Python declarations without executing project code."""

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir.resolve()

    def verify(self, contract: dict) -> ContractVerification:
        checks: list[ContractCheck] = []
        nodes = {str(node["id"]): node for node in contract.get("nodes", [])}
        parsed: dict[str, tuple[Path, ast.Module, dict[str, _Symbol]]] = {}
        for node_id in sorted(nodes):
            self._verify_node(nodes[node_id], parsed, checks)
        for relationship in sorted(
            contract.get("relationships", []),
            key=lambda item: (
                str(item.get("source", "")),
                str(item.get("target", "")),
                str(item.get("relation", "")),
            ),
        ):
            self._verify_relationship(relationship, nodes, parsed, checks)
        return ContractVerification(
            snapshot_id=str(contract.get("snapshot_id", "")),
            task_id=str(contract.get("task", {}).get("id", "")),
            checks=tuple(checks),
        )

    def _verify_node(
        self,
        node: dict,
        parsed: dict[str, tuple[Path, ast.Module, dict[str, _Symbol]]],
        checks: list[ContractCheck],
    ) -> None:
        node_id = str(node["id"])
        if node.get("verification_scope") == "context":
            checks.append(self._check(node_id, "scope", ContractCheckState.ADVISORY, "context anchor"))
            return
        if node.get("location", "IN_REPOSITORY") != "IN_REPOSITORY":
            checks.append(self._check(node_id, "location", ContractCheckState.ADVISORY, "external node"))
            return
        target_path = str(node.get("target_path", "")).strip()
        path = self._safe_path(target_path)
        if path is None or not path.exists():
            checks.append(
                self._check(
                    node_id,
                    "target_path",
                    ContractCheckState.FAILED,
                    f"required path not found: {target_path or '(empty)'}",
                )
            )
            return
        checks.append(self._check(node_id, "target_path", ContractCheckState.PASSED, target_path))
        expected_kind = str(node.get("kind", "unknown"))
        if expected_kind == "package" and path.is_dir():
            checks.append(self._check(node_id, "kind", ContractCheckState.PASSED, "package directory"))
            return
        if path.suffix.lower() != ".py" or not path.is_file():
            checks.append(
                self._check(node_id, "kind", ContractCheckState.FAILED, "required Python source is not a .py file")
            )
            return
        parsed_source = self._parse(path, target_path, node_id, checks, parsed)
        if parsed_source is None:
            return
        _, tree, symbols = parsed_source
        if expected_kind in {"module", "package"}:
            checks.append(self._check(node_id, "kind", ContractCheckState.PASSED, expected_kind))
            self._verify_docstring(node, tree, checks)
            return
        qualified_name = str(node.get("qualified_name", "")).strip()
        if not qualified_name:
            checks.append(
                self._check(node_id, "qualified_name", ContractCheckState.FAILED, "qualified name is required")
            )
            return
        symbol = self._find_symbol(qualified_name, symbols)
        if symbol is None:
            checks.append(
                self._check(
                    node_id,
                    "qualified_name",
                    ContractCheckState.FAILED,
                    f"symbol not found: {qualified_name}",
                )
            )
            return
        if symbol.kind != expected_kind:
            checks.append(
                self._check(
                    node_id,
                    "kind",
                    ContractCheckState.FAILED,
                    f"expected {expected_kind}, found {symbol.kind}",
                )
            )
        else:
            checks.append(self._check(node_id, "kind", ContractCheckState.PASSED, expected_kind))
        self._verify_docstring(node, symbol.node, checks)
        signature = str(node.get("signature", "")).strip()
        if signature and expected_kind in {"function", "method"}:
            self._verify_signature(node_id, signature, symbol.node, checks)

    def _parse(
        self,
        path: Path,
        target_path: str,
        node_id: str,
        checks: list[ContractCheck],
        parsed: dict[str, tuple[Path, ast.Module, dict[str, _Symbol]]],
    ) -> tuple[Path, ast.Module, dict[str, _Symbol]] | None:
        if target_path in parsed:
            return parsed[target_path]
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError, UnicodeError) as error:
            checks.append(self._check(node_id, "syntax", ContractCheckState.FAILED, str(error)))
            return None
        value = (path, tree, _symbols(tree))
        parsed[target_path] = value
        return value

    def _safe_path(self, target_path: str) -> Path | None:
        if not target_path:
            return None
        candidate = Path(target_path)
        if candidate.is_absolute():
            return None
        resolved = (self.project_dir / candidate).resolve()
        if resolved != self.project_dir and self.project_dir not in resolved.parents:
            return None
        return resolved

    @staticmethod
    def _find_symbol(qualified_name: str, symbols: dict[str, _Symbol]) -> _Symbol | None:
        if qualified_name in symbols:
            return symbols[qualified_name]
        matches = [symbol for name, symbol in symbols.items() if qualified_name.endswith(f".{name}")]
        return matches[0] if len(matches) == 1 else None

    def _verify_docstring(self, contract: dict, declaration: ast.AST, checks: list[ContractCheck]) -> None:
        required = bool(str(contract.get("docstring", "")).strip())
        if not required:
            return
        node_id = str(contract["id"])
        present = bool(ast.get_docstring(declaration, clean=False))
        checks.append(
            self._check(
                node_id,
                "docstring",
                ContractCheckState.PASSED if present else ContractCheckState.FAILED,
                "present" if present else "required docstring is missing",
            )
        )

    def _verify_signature(
        self,
        node_id: str,
        signature: str,
        declaration: ast.AST,
        checks: list[ContractCheck],
    ) -> None:
        if not isinstance(declaration, (ast.FunctionDef, ast.AsyncFunctionDef)):
            checks.append(self._check(node_id, "signature", ContractCheckState.FAILED, "symbol is not callable"))
            return
        try:
            expected = ast.parse(f"def __contract{signature}:\n    pass\n").body[0]
        except SyntaxError as error:
            checks.append(
                self._check(node_id, "signature", ContractCheckState.FAILED, f"invalid contract signature: {error.msg}")
            )
            return
        assert isinstance(expected, ast.FunctionDef)
        expected_parameters = _parameters(expected.args)
        actual_parameters = _parameters(declaration.args)
        if [(item.name, item.kind) for item in expected_parameters] != [
            (item.name, item.kind) for item in actual_parameters
        ]:
            checks.append(
                self._check(
                    node_id,
                    "signature.parameters",
                    ContractCheckState.FAILED,
                    "parameter names, order, or kinds differ",
                )
            )
        else:
            checks.append(
                self._check(node_id, "signature.parameters", ContractCheckState.PASSED, "names and order match")
            )
        for expected_parameter, actual_parameter in zip(expected_parameters, actual_parameters, strict=False):
            name = expected_parameter.name
            self._compare_annotation(
                node_id,
                f"signature.{name}.annotation",
                expected_parameter.annotation,
                actual_parameter.annotation,
                checks,
            )
            if expected_parameter.has_default != actual_parameter.has_default:
                checks.append(
                    self._check(
                        node_id,
                        f"signature.{name}.default",
                        ContractCheckState.FAILED,
                        "default presence differs",
                    )
                )
            else:
                checks.append(
                    self._check(
                        node_id,
                        f"signature.{name}.default",
                        ContractCheckState.PASSED,
                        "default presence matches",
                    )
                )
        self._compare_annotation(
            node_id,
            "signature.return",
            expected.returns,
            declaration.returns,
            checks,
        )

    def _compare_annotation(
        self,
        node_id: str,
        field: str,
        expected: ast.expr | None,
        actual: ast.expr | None,
        checks: list[ContractCheck],
    ) -> None:
        same = _ast_equal(expected, actual)
        checks.append(
            self._check(
                node_id,
                field,
                ContractCheckState.PASSED if same else ContractCheckState.FAILED,
                "annotation matches"
                if same
                else f"expected {_annotation(expected)}, found {_annotation(actual)}",
            )
        )

    def _verify_relationship(
        self,
        relationship: dict,
        nodes: dict[str, dict],
        parsed: dict[str, tuple[Path, ast.Module, dict[str, _Symbol]]],
        checks: list[ContractCheck],
    ) -> None:
        source_id = str(relationship.get("source", ""))
        target_id = str(relationship.get("target", ""))
        relation = str(relationship.get("relation", ""))
        level = str(relationship.get("verification_level", "advisory"))
        field = f"relationship.{relation}"
        if level != "hard":
            checks.append(
                self._check(source_id, field, ContractCheckState.ADVISORY, f"{level} relationship")
            )
            return
        source = nodes.get(source_id)
        target = nodes.get(target_id)
        if source is None or target is None:
            checks.append(
                self._check(source_id, field, ContractCheckState.FAILED, "relationship endpoint contract missing")
            )
            return
        if relation == "contains":
            passed = _contains(source, target)
        elif relation == "inherits":
            passed = self._inherits(source, target, parsed)
        else:
            passed = False
        checks.append(
            self._check(
                source_id,
                field,
                ContractCheckState.PASSED if passed else ContractCheckState.FAILED,
                f"{source_id} {relation} {target_id}"
                if passed
                else f"hard relationship not materialized: {source_id} -{relation}-> {target_id}",
            )
        )

    def _inherits(
        self,
        source: dict,
        target: dict,
        parsed: dict[str, tuple[Path, ast.Module, dict[str, _Symbol]]],
    ) -> bool:
        parsed_source = parsed.get(str(source.get("target_path", "")))
        if parsed_source is None:
            return False
        symbol = self._find_symbol(str(source.get("qualified_name", "")), parsed_source[2])
        if symbol is None or not isinstance(symbol.node, ast.ClassDef):
            return False
        expected = str(target.get("qualified_name", ""))
        expected_short = expected.rsplit(".", 1)[-1]
        bases = {ast.unparse(base) for base in symbol.node.bases}
        return expected in bases or expected_short in bases

    @staticmethod
    def _check(
        node_id: str,
        field: str,
        state: ContractCheckState,
        detail: str,
    ) -> ContractCheck:
        return ContractCheck(node_id, field, state, detail)


def _symbols(tree: ast.Module) -> dict[str, _Symbol]:
    symbols: dict[str, _Symbol] = {}

    def visit(body: list[ast.stmt], prefix: str = "", inside_class: bool = False) -> None:
        for declaration in body:
            if isinstance(declaration, ast.ClassDef):
                name = f"{prefix}.{declaration.name}" if prefix else declaration.name
                symbols[name] = _Symbol("class", declaration)
                visit(declaration.body, name, True)
            elif isinstance(declaration, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = f"{prefix}.{declaration.name}" if prefix else declaration.name
                symbols[name] = _Symbol("method" if inside_class else "function", declaration)

    visit(tree.body)
    return symbols


def _parameters(arguments: ast.arguments) -> list[_Parameter]:
    positional = [*arguments.posonlyargs, *arguments.args]
    default_offset = len(positional) - len(arguments.defaults)
    result = [
        _Parameter(
            argument.arg,
            "positional_only" if index < len(arguments.posonlyargs) else "positional",
            argument.annotation,
            index >= default_offset,
        )
        for index, argument in enumerate(positional)
    ]
    if arguments.vararg is not None:
        result.append(_Parameter(arguments.vararg.arg, "vararg", arguments.vararg.annotation, False))
    result.extend(
        _Parameter(argument.arg, "keyword_only", argument.annotation, default is not None)
        for argument, default in zip(arguments.kwonlyargs, arguments.kw_defaults, strict=True)
    )
    if arguments.kwarg is not None:
        result.append(_Parameter(arguments.kwarg.arg, "kwarg", arguments.kwarg.annotation, False))
    return result


def _ast_equal(left: ast.AST | None, right: ast.AST | None) -> bool:
    if left is None or right is None:
        return left is right
    return ast.dump(left, include_attributes=False) == ast.dump(right, include_attributes=False)


def _annotation(value: ast.expr | None) -> str:
    return "(missing)" if value is None else ast.unparse(value)


def _contains(source: dict, target: dict) -> bool:
    source_kind = str(source.get("kind", ""))
    source_path = str(source.get("target_path", "")).replace("\\", "/")
    target_path = str(target.get("target_path", "")).replace("\\", "/")
    source_name = str(source.get("qualified_name", "")).strip(".")
    target_name = str(target.get("qualified_name", "")).strip(".")
    if source_kind in {"module", "package"}:
        if source_kind == "module":
            return source_path == target_path
        return target_path.startswith(source_path.rstrip("/") + "/") or source_path == target_path
    return bool(source_name and target_name.startswith(source_name + "."))
