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
- Control plane local versionado con snapshots, documentos, mapa de diseno y eventos.
- Worker HTTP autenticado para clientes independientes como Graph Lab.
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

## Worker y API local

`mission-worker` es el limite de integracion para interfaces externas. Escucha
solo en loopback, imprime un unico handshake JSON al arrancar y exige el token
de ese handshake en el resto de peticiones. El Host que crea el proceso debe
mantener el token fuera del navegador.

```powershell
.\.venv\Scripts\python.exe -m mission_orchestrator.worker `
	--project C:\ruta\proyecto `
	--task "Implementar la mision" `
	--branch feature/mision `
	--mode full
```

El contrato se publica en `/api/v1/openapi.json`; las capacidades negociables,
en `/api/v1/capabilities`. Snapshots, documentos y operaciones de diseno usan
revisiones para detectar escrituras obsoletas.

En modo interactivo, cada tarea pasa por `spec` y `plan` antes de poder
ejecutarse. Un cambio de diseno durante la ejecucion se detiene en el siguiente
limite de fase y exige una nueva aprobacion. Al terminar, HARNESS versiona
`mission-report.md`; solo hace commit y merge si la reconciliacion entre el
diseno aprobado y el codigo observado abre el gate final.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

