# A2 — Emisión incremental del progreso del agente

Spec completa. Anillo 1, tarea A2. Referencia: visión §12 ("la emisión incremental del puerto del agente y la tabla de eventos" abren los anillos) y §11 (la tabla de eventos alimenta al humano).

## 1. Problema

Tras A1, la tabla de eventos recibe notificaciones y métricas, pero el progreso vivo de una fase —cuándo empieza, qué herramientas usa el agente, cómo termina— solo existe como texto en `mission.log`. La UI (A5) necesita ese pulso como eventos estructurados: es lo que convierte "la misión está corriendo" en algo observable.

## 2. Contrato

### 2.1 Eventos nuevos

| Kind | Emisor | Payload |
|---|---|---|
| `phase_started` | `PhaseExecutor.run`, antes de invocar al agente | `{"phase", "mode"}` |
| `phase_ended` | `PhaseExecutor.run`, en cada salida | éxito: `{"phase", "outcome": "completed", "turns", "input_tokens", "output_tokens", "elapsed_seconds"}`; bloqueo: `{"phase", "outcome": "blocked", "block_kind", "detail"}` (timeout, max_turns, api_retries, gate_fail) |
| `tool_call` | `PublishingLogger.tool_call` (puente de A1, ahora publica además de delegar) | `{"tool", "summary"}` con el mismo resumen legible del logger de fichero |

`phase_ended` es el evento de ciclo de vida; la métrica `phase` existente (tokens/duración vía puente A1) se mantiene sin cambios — semánticas distintas, sin fusionar.

### 2.2 `AppServices.events` (supersede D-A1.5)

`AppServices` gana `events: EventPublisher` con default `NullEventPublisher` (implementación nula en `ports/events.py`, patrón `NoopCodeGraphService`). A2 lo justifica: `PhaseExecutor` — código de aplicación — publica directamente. El default nulo mantiene intactas todas las fixtures existentes.

### 2.3 Resumen de tool compartido

La tabla de descripciones legibles (`Read → "Reading <path>"`, …) sale de `FilesystemMissionLogger` a la función de módulo `describe_tool_call(name, input)` en el mismo fichero; logger y puente la comparten (una sola fuente para el mismo texto en log y evento).

### 2.4 Resiliencia

`publish` mantiene el contrato de A1 (el adaptador nunca propaga); el código de aplicación llama al puerto sin defensas adicionales.

## 3. Criterios de aceptación

- **P1** Una fase exitosa publica `phase_started` (con `phase` y `mode`) antes que cualquier otro evento de la fase, y `phase_ended` con `outcome="completed"`, turnos y tokens al final.
- **P2** Una fase cuyo agente lanza un error de loop (p. ej. reintentos agotados) publica `phase_ended` con `outcome="blocked"` y `block_kind="api_retries"`.
- **P3** Una fase cuyo gate falla publica `phase_ended` con `outcome="blocked"` y `block_kind="gate_fail"`.
- **P4** `PublishingLogger.tool_call` publica `tool_call` con `tool` y `summary` legible, y sigue delegando en el logger interior.
- **P5** El default `NullEventPublisher` no publica ni falla: las composiciones existentes (tests, fixtures) funcionan sin cambios.
- **P6** La suite previa (99 tests) permanece verde.

## 4. Fuera de alcance

- Texto intermedio del agente (mensajes de turno) como eventos — se añadirá si la UI lo reclama.
- Correlación `task_id` en eventos de fase: el executor no conoce la tarea; los eventos de tarea ya existen (`review_verdict`, `rework`). Diferido a que la UI demuestre necesitarlo.
- Transporte (A3) y render (A5).
