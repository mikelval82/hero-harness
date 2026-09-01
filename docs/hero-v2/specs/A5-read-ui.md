# A5 — UI de lectura

Spec completa. Anillo 1, tarea A5. Referencia: visión §10 ("La UI empieza en modo lectura: snapshot, zoom, evidencia, intención, historial y conversación… Un prototipo ligero puede validar el contrato sin una cadena de frontend compleja") y §7 (el humano participa del diseño viendo el mapa, no prosa).

## 1. Problema

Todo el contrato existe (A3 lectura, A4 comandos) pero el humano sigue sin ver el pizarrón. A5 entrega la experiencia que justifica el anillo: el mapa de diseño visible, el diff pendiente delante de los ojos y los botones de aprobar/rechazar en el mismo sitio.

## 2. Contrato

### 2.1 Un solo fichero estático, sin cadena de frontend

- `adapters/web/static/index.html` — HTML+CSS+JS inline, cero dependencias externas (sin CDN, sin npm, funciona offline). Si los gestos de edición del anillo 2 desbordan este prototipo, se adoptará una librería de grafos madura como dependencia opcional (§10); no antes.
- El servidor sirve `GET /` con ese fichero (el placeholder de A3 queda como fallback si el estático no existe). Registrado como package-data.
- La UI consume **exclusivamente** los endpoints de A3/A4 con el token de la URL (`?token=…`); nunca toca SQLite ni ficheros.

### 2.2 Funcionalidad

| Zona | Contenido |
|---|---|
| Lienzo SVG | Grafo por capas de nivel (SYSTEM/PACKAGE/CODE en filas); nodos coloreados por intent (CREATE verde, CHANGE ámbar, REMOVE rojo, KEEP neutro); edges con flecha y etiqueta de relación; tooltip con locator y descripción; **zoom** con rueda y **pan** con arrastre (viewBox) |
| Cabecera | Misión, `design_revision`, snapshot aprobado (id) si existe |
| Panel diff | Texto de `/api/diff` (idéntico al de stdin/Telegram) + botones **Aprobar** / **Rechazar** (pide razón) / campo de respuesta libre → `POST /api/command` |
| Feed de eventos | Long-poll continuo de `/api/events` (`after` incremental, `wait=25`); cada evento nuevo refresca mapa, diff y snapshot |
| Historial | Operaciones del `DesignStore` (`/api/history`) |

### 2.3 Comportamiento reactivo

Bucle de long-poll: al llegar eventos se anotan en el feed (hora + kind + resumen legible) y se refrescan mapa/diff/snapshot. Sin eventos, la UI queda en espera silenciosa (sin polling agresivo).

## 3. Criterios de aceptación

Automatizables (suite):

- **U1** `GET /` con token devuelve `text/html` con la aplicación (marcadores: lienzo SVG, panel de diff, botones de comando).
- **U2** El HTML no referencia recursos externos (sin `http(s)://` hacia terceros, sin CDN): funciona en local puro.
- **U3** El JS consume solo los contratos públicos (`/api/map`, `/api/diff`, `/api/snapshot`, `/api/history`, `/api/events`, `/api/command`).
- **U4** Sin el fichero estático el servidor cae al placeholder (compatibilidad A3 intacta).
- **U5** La suite previa (119 tests) permanece verde.

Visuales (checkpoint A6, navegador real): grafo renderizado con intents distinguibles, zoom/pan operativos, aprobar desde la UI desbloquea una misión real.

## 4. Fuera de alcance

- Edición desde el lienzo (anillo 2).
- Layout jerárquico por `parent_id`, agrupación visual de paquetes — cuando el mapa real lo pida.
- Autenticación más allá del token de sesión de A3.
