# K10 — Diff textual del mapa y telemetría mínima

Spec ligera. Cierra el circuito humano y el de medición: quien aprueba ve *qué* aprueba (no solo un recuento), y la misión deja rastro estructurado de lo que la hipótesis HERO necesita medir. Deriva de las secciones 9, 11 y 13 de [hero-v2-grafo-vivo.md](../../hero-v2-grafo-vivo.md).

## 1. Alcance

Entra: `render_map_diff` puro en dominio, integración en el aviso de aprobación, eventos de telemetría vía `logger.metric` (aprobación, veredicto de review, retrabajo, reconciliación).

No entra: UI/transporte (anillo posterior); telemetría especulativa — solo los eventos que la evaluación de la visión §11 declara (veredicto inicial, retrabajo, cobertura y deriva); identificadores de correlación extra (llegan cuando exista el anillo que los use).

## 2. Decisiones de contrato

**El diff es una proyección pura del mapa.** `render_map_diff(nodes, edges)` produce texto determinista agrupado por intención: `+` CREATE, `~` CHANGE, `-` REMOVE, con label, nivel y locator/descripción cuando existen; los KEEP se resumen en una línea (`= KEEP: n`) para no ahogar la señal; los edges no-KEEP se listan con su relación. Mapa sin cambios → "no proposed changes". Sin estado, sin I/O.

**Se muestra antes de decidir.** `ApprovalCoordinator` notifica el diff justo antes del resumen de aprobación existente, de modo que stdin/Telegram reciben el detalle y luego la pregunta. En la re-presentación tras CONFLICT se vuelve a renderizar el mapa vigente.

**Telemetría = eventos JSONL sobre el canal existente.** Sin infraestructura nueva: `logger.metric` ya escribe `_metrics.jsonl` por misión (la correlación por misión es el propio fichero). Eventos:

| Evento | Cuándo | Campos |
|--------|--------|--------|
| `approval` | snapshot aprobado | `snapshot_id`, `design_revision`, `observed_revision` |
| `review_verdict` | primer veredicto de review por tarea | `task_id`, `verdict`, `attempt` |
| `rework` | cada reimplementación | `task_id`, `cause` (`minor_changes` / `human_retry`) |
| `reconciliation` | gate de merge evaluado | `snapshot_id`, `counts` por estado, `gate` (`open`/`blocked`) |

"Retrabajo" sigue la definición de la visión §11: nueva ejecución causada por revisión o corrección humana, no cualquier conversación extra.

**El logger nunca rompe la misión.** `metric` ya traga excepciones; los emisores no añaden manejo propio.

## 3. Tabla de aceptación

| # | Caso | Resultado esperado |
|---|------|--------------------|
| D1 | Mapa con CREATE+CHANGE+REMOVE+KEEP y edges nuevos | diff con `+`/`~`/`-`, resumen `= KEEP: n`, edges listados; determinista |
| D2 | Mapa solo KEEP | "no proposed changes" |
| D3 | Aprobación con mapa | el notifier recibe el diff antes del resumen; `approval` emitido con snapshot y revisiones |
| D4 | Review con veredicto inicial APPROVED / MINOR_CHANGES | `review_verdict` con attempt 1; MINOR_CHANGES emite además `rework` con causa `minor_changes` |
| D5 | `/retry` humano | `rework` con causa `human_retry` |
| D6 | Gate evaluado con divergencia / limpio | `reconciliation` con counts y `gate` correcto |
| D7 | Misiones sin mapa/changeset | ningún evento nuevo ni diff; suite previa verde |

## 4. Verificación

`tests/application/test_diff_and_telemetry.py` codifica D1–D6; D7 la cubre la suite existente. Auditoría: diff limitado a domain/map_diff.py, application/approval.py, application/review_coordinator.py, application/orchestrator.py (emisión reconciliation), tests y worklog.
