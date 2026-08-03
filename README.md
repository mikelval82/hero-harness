# Mission Orchestrator v2

Reimplementacion pragmatica del harness como orquestador de misiones LLM con
core desacoplado, artefactos markdown/json como contrato operativo y adapters
para filesystem, tools locales, Git, Telegram, stdin, Anthropic y code graph.

## Estado

Este repo contiene una primera base funcional:

- Dominio y puertos puros.
- `AppServices` como composition root sin framework DI.
- Pipeline por modos `full`, `focused`, `plan`, `explore` y `hotfix`.
- Adapters filesystem para artefactos, tareas, estado, workspace y registry.
- Tools `Read`, `Write`, `Edit`, `Glob`, `Grep` y `Bash` con politica de rutas.
- CommandBus unico con listeners stdin/Telegram.
- Gate evaluator, HITL basico, compactacion, report y Git service.
- Code graph SQLite incremental basado en `ast` de Python.
- Tests sin Anthropic, Telegram real ni Git real.

## Uso

```powershell
.\.venv\Scripts\python.exe -m mission_orchestrator.cli "Implement foo" feature/foo --mode plan
```

Para usar el script `mission`, instala el paquete en editable:

```powershell
uv pip install -e .
```

El adapter Anthropic es opcional. Sin `anthropic` instalado o sin
`ANTHROPIC_API_KEY`, el CLI fallara claramente al intentar ejecutar una fase que
requiera modelo real.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

