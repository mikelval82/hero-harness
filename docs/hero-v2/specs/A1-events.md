# A1 — Puerto `EventPublisher` y tabla de eventos

Spec completa. Anillo 1, tarea A1. Referencia: visión §11 ("publicador de eventos de misión" como puerto de capacidad; "la tabla de eventos" alimenta al humano) y §12 (primer anillo: "la emisión incremental del puerto del agente y la tabla de eventos").

## 1. Problema

Todo lo que el humano puede saber de una misión en curso viaja hoy por tres canales efímeros o de bajo nivel: `print`/`mission.log` (prosa sin estructura), el notifier (mensajes puntuales sin historia consultable) y `_metrics.jsonl` (estructurado pero sin correlación uniforme ni orden garantizado para consumo incremental). La UI del anillo 1 (A3–A5) necesita una fuente única, ordenada, append-only y consultable desde un id: la tabla de eventos.

## 2. Contrato

### 2.1 Dominio — `MissionEvent` (`domain/event.py`)

Dataclass congelada:

| Campo | Tipo | Semántica |
|---|---|---|
| `event_id` | `int` | Monótono creciente por misión; asignado por el almacén, nunca por el emisor |
| `timestamp` | `str` | ISO-8601 con segundos |
| `mission` | `str` | Tag de la misión (`mission_tag`) |
| `kind` | `str` | Tipo del evento (`notification`, `mission_result`, `approval`, `review_verdict`, `rework`, `reconciliation`, `phase`, `metric`, …) |
| `payload` | `dict` | Contenido íntegro del evento, JSON-serializable |
| `task_id` | `str \| None` | Correlación, extraída del payload si existe |
| `snapshot_id` | `str \| None` | Correlación, extraída del payload si existe |

### 2.2 Puerto — `EventPublisher` (`ports/events.py`)

```python
class EventPublisher(Protocol):
    def publish(self, kind: str, payload: dict) -> None: ...
    def events_since(self, after_id: int, limit: int = 200) -> list[MissionEvent]: ...
```

- `publish` es fire-and-forget: **nunca** propaga excepciones a la misión (mismo contrato de resiliencia que `FilesystemMissionLogger`).
- `events_since(0)` devuelve desde el principio; el resultado viene ordenado por `event_id` ascendente y acotado por `limit`. Es el contrato de long-poll/SSE que consumirá A3.

### 2.3 Adaptador — `SqliteEventLog` (`adapters/events/sqlite_log.py`)

- Fichero `events.db` en el directorio de misión (junto a `design.db`/`code_graph.db`).
- Tabla `events(id INTEGER PRIMARY KEY AUTOINCREMENT, ts, mission, kind, task_id, snapshot_id, payload)`; append-only, sin UPDATE ni DELETE.
- Conexión por operación (los listeners y el orquestador viven en hilos distintos; sqlite por conexión efímera evita estado compartido).
- La correlación se extrae del payload: claves `task_id` y `snapshot_id` cuando estén presentes.

### 2.4 Puentes — decoradores sobre puertos existentes (`adapters/events/decorators.py`)

Cobertura completa sin tocar ningún call-site:

- `PublishingNotifier(inner, events)`: `notify(msg)` publica `kind="notification"`, `payload={"message": msg}` y delega; `notify_result(result)` publica `kind="mission_result"`, `payload={"outcome", "summary", "completed", "failed"}` y delega.
- `PublishingLogger(inner, events)`: `metric(record)` publica y delega; `log`/`tool_call` solo delegan (la emisión incremental de progreso es A2, no A1). El `kind` se deriva: `record["event"]` si existe; si no, `"phase"` cuando el registro trae clave `phase` (métricas de fase del executor); si no, `"metric"`.

### 2.5 Cableado

- `cli.py`: construye `SqliteEventLog` sobre el directorio de misión y envuelve notifier y logger con los decoradores. Nada más cambia.
- `AppServices` **no** gana campo en A1: ningún servicio de aplicación consume eventos todavía (los puentes cubren la emisión). El campo se añade en A3, cuando el servidor lea `events_since`.

## 3. Criterios de aceptación

- **E1** `publish` persiste y `events_since(0)` devuelve el evento con `event_id` monótono, `kind`, `mission` y payload íntegro (roundtrip JSON).
- **E2** `task_id`/`snapshot_id` se rellenan cuando el payload los trae; quedan `None` cuando no.
- **E3** `events_since(after_id)` devuelve solo eventos posteriores, en orden ascendente, respetando `limit`.
- **E4** Los eventos sobreviven a la reapertura del almacén (nueva instancia sobre el mismo directorio sigue la numeración).
- **E5** `PublishingNotifier` publica `notification`/`mission_result` con el payload especificado y siempre delega en el interior.
- **E6** `PublishingLogger.metric` publica con el `kind` derivado (evento nombrado → su nombre; métrica de fase → `phase`) y siempre delega.
- **E7** Un `EventPublisher` que lanza excepciones no impide que notifier/logger interiores reciban la llamada (resiliencia de los puentes) y `SqliteEventLog.publish` no propaga errores propios.
- **E8** La suite previa (91 tests) permanece verde.

## 4. Fuera de alcance

- Emisión incremental de progreso del agente (A2).
- Transporte HTTP/SSE y autenticación (A3).
- Retención/compactación de la tabla (diferido hasta que la escala lo pida).
