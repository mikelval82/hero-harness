# A3 — Servidor HTTP local de lectura

Spec completa. Anillo 1, tarea A3. Referencia: visión §10 (transporte: `127.0.0.1`, token por sesión, validación de origen, long polling sancionado explícitamente; "la interfaz consume contratos públicos del núcleo, no lee tablas SQLite directamente") y §11 (puertos como capacidades; HTTP y la UI son adaptadores reemplazables).

## 1. Problema

El estado del mapa, el diff pendiente, el snapshot aprobado, el historial y la tabla de eventos existen y están completos (K4–K7, A1–A2), pero solo son accesibles leyendo ficheros y SQLite a mano. La UI de lectura (A5) necesita un transporte: un servidor local que exponga esos contratos como JSON y entregue eventos de forma incremental.

## 2. Contrato

### 2.1 Adaptador — `MissionWebServer` (`adapters/web/server.py`)

- `MissionWebServer(harness_dir, mission, host="127.0.0.1", port=0)`; `start()` arranca un `ThreadingHTTPServer` en hilo daemon y devuelve la URL base con token; `stop()` lo apaga. `port=0` → puerto efímero del SO.
- El servidor **compone adaptadores existentes** (`DesignStore`, `SqliteEventLog`, `approved_snapshot.json`): el navegador solo ve JSON de contratos públicos, nunca SQLite.
- Solo métodos GET; la escritura (comandos) es A4.

### 2.2 Seguridad (§10)

- Escucha únicamente en `127.0.0.1`.
- **Token por sesión**: `secrets.token_urlsafe` generado al construir; toda petición debe traerlo (`Authorization: Bearer <t>` o query `?token=<t>`); si falta o no coincide → `401`.
- **Validación de origen**: si la petición trae cabecera `Origin` cuyo host no es `127.0.0.1`/`localhost` → `403` (bloquea webs remotas usando el navegador como proxy).
- Sin política de rutas de filesystem: no hay endpoint que reciba rutas (solo lectura de contratos fijos).

### 2.3 Endpoints

| Ruta | Respuesta |
|---|---|
| `GET /` | HTML mínimo de comprobación (A5 lo sustituye por la UI) |
| `GET /api/map` | `{"design_revision", "nodes": [...], "edges": [...]}` desde `DesignStore` |
| `GET /api/diff` | `{"design_revision", "text"}` con el render de `render_map_diff` (K10): el mismo texto que ve stdin/Telegram |
| `GET /api/snapshot` | Contenido de `approved_snapshot.json`, o `null` si no hay aprobación |
| `GET /api/history` | Registro de operaciones del `DesignStore` (`seq`, `operation_id`, `author`, `base_revision`, `status`, `detail`) |
| `GET /api/events?after=N&wait=S` | `{"events": [...]}` desde `SqliteEventLog.events_since(N)`; con `wait>0` (tope 30 s) hace long-poll: espera hasta que haya eventos nuevos o venza el plazo |
| otra ruta | `404` |

Respuestas JSON con `Cache-Control: no-store`.

### 2.4 Cableado

- `cli.py`: flags `--web` (bool) y `--web-port` (int, default `8765`). Con `--web`, arranca el servidor tras montar servicios y registra la URL con token en el log. Hilo daemon: no impide la salida del proceso. Sin `--web`, nada cambia — el modo headless es idéntico.

## 3. Criterios de aceptación

- **W1** Petición sin token o con token erróneo → `401`; con token válido → `200`.
- **W2** `Origin` de host ajeno → `403`; `Origin` local o ausente → pasa.
- **W3** `/api/map` devuelve `design_revision`, nodos y edges sembrados en el `DesignStore`.
- **W4** `/api/diff` devuelve el texto de `render_map_diff` (contiene las líneas `+ CREATE …`).
- **W5** `/api/snapshot` devuelve `null` sin aprobación y el JSON del snapshot cuando existe.
- **W6** `/api/events?after=N` devuelve exactamente los eventos posteriores a `N` publicados en `events.db`.
- **W7** Ruta desconocida → `404`; `/api/history` lista las operaciones aplicadas.
- **W8** La suite previa (105 tests) permanece verde.

## 4. Fuera de alcance

- Mutaciones (`/approve`, `/reject`, `/abort`) — A4.
- UI estática real — A5.
- SSE/WebSocket: el long-poll cumple §10 para el MVP; se sustituirá solo con necesidad demostrada.
