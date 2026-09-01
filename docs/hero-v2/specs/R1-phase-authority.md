# R1 — Autoridad efectiva por fase

**Estado:** implementada localmente; pendiente de CI/PR

## Decisión

La lista de herramientas anunciada a un proveedor no es una frontera de seguridad. Cada fase resuelve una única `PhaseAuthority` y esa misma autoridad gobierna dos puntos del runtime:

1. los schemas que se anuncian al proveedor;
2. el dispatch real de cada tool call en `LocalToolRegistry`.

Una autoridad ausente, una herramienta no declarada, una escritura fuera del scope o una mutación de grafo no permitida se rechazan antes de ejecutar la herramienta. El rechazo bloquea la fase con `BlockKind.POLICY` y deja telemetría `tool_rejected` sin contenido de la llamada ni secretos.

## Matriz R1

| Fase | Proyecto | Artefactos HARNESS permitidos | Mutación especial | Tools |
|---|---|---|---|---|
| Research | Solo lectura | `brainstorm.md` | `GraphPropose` | Read, Glob, Grep, Write, GraphQuery, GraphPropose |
| Structure | Solo lectura | `tasks.json` | — | Read, Glob, Grep, Write |
| Grill | Solo lectura | `brief.md` | `GraphPropose` | Read, Glob, Grep, Write, GraphQuery, GraphPropose |
| Spec | Solo lectura | `spec.md` | — | Read, Glob, Grep, Write |
| Plan | Solo lectura | `plan.md`, `decisions.md` | — | Read, Glob, Grep, Write |
| Implement | Escritura | `status.md` | — | Read, Glob, Grep, Write, Edit, Bash |
| Implement bursts | Escritura | `_burst_progress.md`, `status.md` | — | Read, Glob, Grep, Write, Edit, Bash |
| Review | Solo lectura | `audit.md` | — | Read, Glob, Grep, Write |
| Reimplement | Escritura | `status.md` | — | Read, Glob, Grep, Write, Edit, Bash |
| Compact | Solo lectura | `_compact_tmp.md` | — | Read, Write |
| Consolidate | Solo lectura | `tasks.json` | — | Read, Write |
| Report / Report plan | Solo lectura | `mission-report.md` | — | Read, Write, Glob |

Las únicas fases con escritura de proyecto son Implement, Implement bursts y Reimplement. La escritura está permitida en todo el proyecto de forma transitoria: `task-contract.json` todavía no ofrece un conjunto fiable de rutas normalizadas para reducirla a rutas contractuales. Ese estrechamiento queda explícitamente fuera de R1.

## Límites deliberados

R1 no convierte Bash en un sandbox ni filtra todas las credenciales del proceso hijo. El shell genérico se elimina de las fases no implementadoras y la ejecución de Bash se restringe a fases con escritura de proyecto; además, no recibe `CLAUDE_HARNESS` ni un `ToolEnvironment` con acceso al workspace. La política de `argv`, pipes, entorno hijo y validación confiable pertenece a R2.

Las escrituras internas del runtime mediante `ArtifactStore`, state, Git o stores de diseño no son tool calls del proveedor. Conservan sus contratos propios; R1 gobierna la autoridad que se entrega al agente.

## Evidencia de aceptación

- La matriz completa se prueba contra `PHASES`.
- Research, Spec, Plan y Review no pueden escribir el proyecto mediante `Write` o `Edit`.
- Cada fase solo puede escribir sus artefactos HARNESS declarados.
- Anthropic y DeepSeek propagan la autoridad hasta el registry; una llamada inventada termina la fase como política rechazada.
- Un intento de `GraphPropose` desde Spec no llega al store de diseño.
- La autoridad omitida falla cerrada y cada rechazo publica `phase`, `tool` y `reason`.

El seguimiento del programa vive en el [epic de paridad](../main-develop-parity-epic.md).
