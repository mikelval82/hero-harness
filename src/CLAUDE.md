# Style rules — code_graph compatibility

The dependency graph (`code_graph.py`) uses tree-sitter to extract nodes and edges statically.
All production code MUST follow these constraints so the graph captures 100% of the structure.

## Definitions

- **Top-level**: directly inside a module body, not nested inside another function or conditional.

## Rules

1. **Classes and functions must be top-level.** Never define a class or function inside another function. No closures that define named functions; use lambdas only for trivial expressions.

2. **Imports must be absolute.** Write `from src.core.gate import check_gate`, never `from . import gate` or `from .gate import check_gate`. The parser ignores relative imports.

3. **Calls must be direct.** Use `self.method()`, `module.func()`, or `Class()`. Avoid dynamic dispatch (`getattr(obj, name)()`), call-through-variable (`fn = pick(); fn()`), or chained calls (`a.b().c()`) when the intermediate call is what matters for the graph.

4. **Inheritance must be explicit.** Write `class Foo(Base):` with the base class visible as an identifier or `module.Class`. The parser does not resolve strings, `type()` calls, or metaclass tricks.

5. **One class per concern.** When extracting from `mission.py`, each new module should contain one primary class. Node IDs follow the format `filepath:Class.method` — keeping modules focused makes the graph readable.

6. **No nested imports inside functions** for project-internal modules. The graph only resolves imports at module level. Standard-library or third-party lazy imports inside functions are acceptable.

# Format standards

- **Specifications** (`spec.md`): use EARS syntax (Ubiquitous, Event-driven, State-driven, Optional, Unwanted) in `## Comportamiento Esperado` and `## Criterios de Aceptacion`.
- **Decisions** (`decisions.md`): use ADR format (`### ADR-N: Title` / `**Context:**` / `**Decision:**` / `**Consequences:**`).
- **Prompt templates** (`prompts/`): always use `-prompt.md` suffix to distinguish from gate artifacts.

# Test conventions

- Tests live in `src/tests/`.
- Harness runtime is separate from the target repo runtime. Prefer the harness
  venv at `.venv\Scripts\python.exe`; `bin\mission.bat` uses
  `CLAUDE_HARNESS_PYTHON` first, then that venv, then `python`.
- Harness artifacts live under `$CLAUDE_HARNESS`, normally
  `$HOME/.harness/<project>/<branch-safe>/`. The target repo is only for the
  requested code changes and optional `mission-validate.*` script.
- Run harness tests with: `.venv\Scripts\python.exe -m pytest src/tests/ -x -q --ignore=src/tests/test_code_graph.py`
- Target repos validate themselves with `mission-validate.cmd`, `.bat`, `.ps1`,
  or `.sh` in the target project root. Do not run harness tests as target
  validation.
- `src/.env` contains secrets — NEVER commit it.
