# K8 — Scheduling con dependencias y estado `blocked`

Spec ligera. El ejecutor deja de recorrer `tasks.json` en orden de fichero: selecciona la siguiente tarea cuyas dependencias estén completadas, y las tareas cuyo prerequisito falló quedan en `blocked` con la razón, en vez de ejecutarse contra un cimiento inexistente. Deriva de la sección 8 de [hero-v2-grafo-vivo.md](../../hero-v2-grafo-vivo.md); cierra el hueco declarado en la spec de K7 ("No entra: estado `blocked` y scheduling del ejecutor").

## 1. Alcance

Entra: `TaskStatus.BLOCKED`, funciones puras de scheduling en `domain/workplan.py` (`next_runnable_index`, `dependency_block_reason`), bucle del `TaskExecutor` guiado por dependencias, `summarize_tasks` con recuento y detalle de bloqueadas.

No entra: reconciliación y gate de merge (K9); render del diff (K10); ejecución paralela de tareas independientes (fuera del kernel).

## 2. Decisiones de contrato

**Selección determinista.** `next_runnable_index(tasks)` devuelve el índice de la primera tarea `pending` (en orden de lista) con todas sus dependencias `completed`, o `None`. Con `tasks.json` legado (sin dependencias) el orden de ejecución es idéntico al actual: sin mapa no se paga peaje (coherente con D-7.1).

**Fallo aguas arriba = blocked aguas abajo, no failed.** `failed` significa "se intentó y no salió"; una tarea cuyo prerequisito falló no se intentó. `dependency_block_reason` produce la razón (`dependency failed: <id>`, `dependency blocked: <id>`) y el ejecutor la persiste. El bloqueo es transitivo (T3 que depende de T2 bloqueada queda bloqueada).

**El scheduler no re-valida ciclos.** `validate_plan` (K7) certifica el plan antes de ejecutar. Si aun así ninguna tarea es ejecutable y quedan pendientes sin dependencia fallida (ciclo en tasks.json legado editado a mano), se marcan `blocked` con `unresolvable dependencies` y la misión sigue a reporte: nunca bucle infinito.

**Compatibilidad total.** `TaskStatus.parse` ya acepta valores nuevos por iteración del enum; `summarize_tasks` añade `Blocked` al recuento y una línea `BLOCKED [id]: razón` por tarea bloqueada, de modo que el humano ve por qué no se intentó.

## 3. Tabla de aceptación

| # | Caso | Resultado esperado |
|---|------|--------------------|
| D1 | `TaskStatus.parse("blocked")` y roundtrip JSON de una tarea bloqueada | estado y razón se conservan |
| D2 | Lista `[T2(dep T1), T1]` → `next_runnable_index` | selecciona T1 primero; tras completar T1, selecciona T2; sin ejecutables devuelve `None` |
| D3 | `dependency_block_reason` con dep fallida / bloqueada / completadas | razón con el id del prerequisito; `None` si todo completado |
| D4 | `summarize_tasks` con una tarea bloqueada | recuento `Blocked: 1` y línea `BLOCKED [id]` con la razón |
| D5 | Misión con T1 (falla), T2 (depende de T1), T3 (independiente) | T1 `failed`, T2 `blocked` con razón que cita T1, T3 `completed`; misión PARTIAL |
| D6 | `tasks.json` legado sin dependencias | mismo orden y resultados que antes de K8 (suite previa verde) |

## 4. Verificación

`tests/application/test_scheduling.py` codifica D1–D5; D6 la cubre la suite existente del orquestador. Auditoría: diff limitado a domain/task.py, domain/workplan.py, application/task_executor.py, tests y worklog.
