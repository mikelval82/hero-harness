# K9 — Reconciliación y gate de merge

Spec completa. Cierra el circuito con la realidad: tras ejecutar, la misión compara lo aprobado con lo observado y el merge automático deja de depender solo de la ausencia de `BlockReason`. Deriva de la sección 9 de [hero-v2-grafo-vivo.md](../../hero-v2-grafo-vivo.md) y resuelve la observación CP-2 del checkpoint.

## 1. Alcance

Entra: modelo de reconciliación en dominio (`OperationState`, `OperationCheck`, `Reconciliation`, `reconcile`, `merge_gate_reasons`), servicio de aplicación que materializa `reconciliation.json`, integración del gate en `_finalize` del orquestador (reconstrucción final del grafo incluida).

No entra: render del diff y telemetría (K10); reconciliación incremental tras cada tarea con eventos para UI (anillo posterior — la reconstrucción por tarea ya existe en el ejecutor); aceptación interactiva de discrepancias no críticas (v1 las registra sin bloquear).

## 2. Decisiones de contrato

**Cuatro estados por operación, nunca un booleano.** `PENDING` (la tarea que la cubre no completó), `MATERIALIZED` (la evidencia esperada aparece en la observación), `DIVERGENT` (la tarea completó pero la evidencia contradice), `UNVERIFIABLE` (el analyzer no puede pronunciarse). La visión §9 lo exige: "la ausencia de resolución no se interpreta automáticamente como fallo".

**Evidencia por tipo de operación.** Con `observed_ids` (nodos del facts db) como única fuente:

| Operación | Completada y… | Estado |
|-----------|---------------|--------|
| CREATE_NODE con `locator` | locator observado / no observado | MATERIALIZED / DIVERGENT |
| CREATE_NODE sin `locator` | — | UNVERIFIABLE (sin ancla esperada) |
| MODIFY_NODE | ancla sigue observada / desapareció | MATERIALIZED / DIVERGENT |
| REMOVE_NODE | ancla desapareció / sigue observada | MATERIALIZED / DIVERGENT |
| CONNECT / DISCONNECT | — | UNVERIFIABLE (las relaciones no están en el lienzo v1, §6) |

Si la tarea que cubre la operación no está `completed` (pendiente, fallida o bloqueada): `PENDING` con la razón. Una operación sin tarea que la cubra también es `PENDING` ("approved but uncovered") — es una de las condiciones de bloqueo explícitas de la visión.

**Resolución de CP-2.** Los artefactos fuera del alcance del analyzer (no-Python) nunca llegan a la reconciliación como falsa deriva: los CHANGE/REMOVE sin ancla observada ya cayeron como issue en la compilación (K6), y un CREATE sin locator queda `UNVERIFIABLE`, que es no-crítico. "No observado por alcance" termina en UNVERIFIABLE; "no observado porque no existe" (ancla que estaba y desapareció, o locator esperado que no llegó) termina en DIVERGENT.

**El gate evalúa resultado + reconciliación, no solo bloqueos técnicos.** `merge_gate_reasons` devuelve las razones que impiden el merge automático: tarea `failed` o `blocked` (resultado parcial), operación `PENDING` (aprobado sin ejecutar) y operación `DIVERGENT` (divergencia crítica). `UNVERIFIABLE` no bloquea: queda registrada en `reconciliation.json` como aceptación implícita auditable. Lista vacía = merge permitido.

**Sin mapa no hay peaje.** Si no existe `changeset.json`, el gate devuelve `[]` sin computar nada: las misiones clásicas siguen mergeando exactamente como antes (coherente con D-7.1 y D-8.2).

**El gate no es un `BlockReason`.** Un merge denegado no convierte la misión en BLOCKED: el resultado (COMPLETE/PARTIAL) lo sigue determinando el reporte; el gate solo retira el merge automático y notifica las razones. Es la distinción literal de la visión: "impiden el merge automático aunque la misión no tenga un bloqueo técnico global".

**Reconstrucción final antes de reconciliar.** `_finalize` reconstruye el grafo observado una última vez para que la observación incluya el último resultado aceptado (visión §9); la reconstrucción por tarea ya existía en el ejecutor.

## 3. Tabla de aceptación

| # | Caso | Resultado esperado |
|---|------|--------------------|
| D1 | Operación cuya tarea está pendiente / fallida / bloqueada / sin cobertura | `PENDING` con detalle que cita la tarea (o "uncovered") |
| D2 | CREATE con locator observado / no observado / sin locator (tarea completada) | MATERIALIZED / DIVERGENT / UNVERIFIABLE |
| D3 | MODIFY con ancla viva / desaparecida; REMOVE con ancla desaparecida / viva | MATERIALIZED / DIVERGENT (simétricos) |
| D4 | CONNECT y DISCONNECT con tarea completada | UNVERIFIABLE |
| D5 | Gate: tarea fallida, op PENDING u op DIVERGENT → razones; todo MATERIALIZED+UNVERIFIABLE → `[]` | bloqueo selectivo y detallado |
| D6 | `Reconciliation.to_json` | serializa snapshot_id, observed_revision y checks con estado y detalle |
| D7 | Misión con changeset, tareas completadas y divergencia → no merge, `reconciliation.json` escrito, razones notificadas; variante todo verificable/UNVERIFIABLE → merge | gate integrado en `_finalize` |
| D8 | Misión sin `changeset.json` | merge idéntico a antes de K9 (suite previa verde) |

## 4. Verificación

`tests/application/test_reconciliation.py` codifica D1–D7; D8 la cubre la suite existente (`test_task_failure_does_not_abort_next_task` mergea sin changeset). Auditoría: diff limitado a domain/reconciliation.py, application/reconciler.py, application/orchestrator.py, tests y worklog.
