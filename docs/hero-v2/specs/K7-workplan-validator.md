# K7 — WorkPlan, validador y planificación compilada

Spec completa. Cierra la cadena snapshot → changeset → tareas: el structurer agrupa operaciones en entregables, un validador determinista exige cobertura exacta y dependencias válidas, y la consolidación LLM queda desactivada para planes compilados. Deriva de las secciones 8 y 13 de [hero-v2-grafo-vivo.md](../../hero-v2-grafo-vivo.md).

## 1. Alcance

Entra: extensión de `Task` (`covers`, `dependencies`, `target_nodes`), validador puro de dominio, `PlanCompiler` que materializa `changeset.json`, integración del flujo en el orquestador con activación por presencia de mapa, prompt del structurer actualizado, consolidación desactivada para planes compilados.

No entra: estado `blocked` y scheduling del ejecutor (K8); reconciliación y gate de merge (K9); render del diff (K10).

## 2. Decisiones de contrato

**Activación por presencia de mapa, no por modo.** El flujo compilado se activa cuando la misión tiene un mapa de diseño con nodos (`design.db` con contenido). Si researcher/griller no dibujaron nada, la misión sigue el flujo actual sin fricción — es la forma operativa del "opcional por modo" de la visión §13: los modos que no dibujan no pagan peaje, sin necesidad de flags.

**Secuencia en el pipeline.** Justo antes de la fase STRUCTURE: si hay mapa → espera de aprobación (K5) → APPROVED compila y escribe `changeset.json` → STRUCTURE recibe el changeset como include y agrupa → la validación de estructura añade el veredicto de cobertura. REJECTED/ABORTED bloquean la misión con la razón del humano.

**El validador es la garantía; el structurer solo agrupa.** `validate_plan(operation_ids, tasks)` es puro y devuelve errores: operación sin cubrir, cobertura duplicada, `covers` desconocido, dependencia inexistente, auto-dependencia y ciclos. Lista vacía = plan válido. El LLM propone la agrupación; la corrección la certifica el validador — si falla, STRUCTURE bloquea con los errores como detalle.

**`Task` conserva compatibilidad.** Los tres campos nuevos serializan siempre y cargan con default `[]`; un `tasks.json` legado sigue siendo válido (misiones sin mapa no cambian).

**Sin consolidación LLM sobre planes compilados.** `consolidate_tasks` podría perder cobertura o dependencias; con `changeset.json` presente no se invoca.

## 3. Tabla de aceptación

| # | Caso | Resultado esperado |
|---|------|--------------------|
| D1 | Plan con cobertura exacta y deps válidas | `validate_plan` devuelve `[]` |
| D2 | Operación sin cubrir / cubierta dos veces / `covers` con id desconocido | un error por cada caso, mensaje identifica la operación |
| D3 | Dependencia a tarea inexistente / auto-dependencia / ciclo T1→T2→T1 | errores detectados |
| D4 | Roundtrip JSON de `Task` con los campos nuevos; carga de JSON legado sin ellos | conserva listas; legado carga con `[]` |
| D5 | `PlanCompiler` con `approved_snapshot.json` + facts db | escribe `changeset.json` determinista con las operaciones esperadas; sin snapshot no escribe nada |
| D6 | Misión con mapa + `/approve` encolado + structurer que cubre todo | misión COMPLETE; `changeset.json` y `approved_snapshot.json` existen |
| D7 | Misión con mapa + `/approve` + structurer que no cubre operaciones | BLOCKED en structure con detalle de cobertura |
| D8 | Misión con mapa + `/reject` | BLOCKED con razón del humano; no se compila changeset |
| D9 | Misión sin mapa | flujo actual intacto (los tests previos del orquestador siguen verdes) |

## 4. Verificación

`tests/application/test_plan_pipeline.py` codifica D1–D8; D9 la cubre la suite existente del orquestador. Auditoría: diff limitado a domain/task.py, domain/workplan.py, application/plan_compiler.py, application/orchestrator.py, application/report_service.py (guard), application/phase_registry.py, domain/mission.py + cli.py (project_scope_dir), prompts/structure-prompt.md, agents/structurer.md, tests y worklog.
