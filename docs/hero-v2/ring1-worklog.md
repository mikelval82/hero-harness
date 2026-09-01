# HERO v2 — Anillo 1 "El mapa visible": estructura de trabajo y auditoría

Cuaderno de trabajo del primer anillo posterior al kernel, descrito en [hero-v2-grafo-vivo.md](../hero-v2-grafo-vivo.md) (secciones 10 y 12). Mismo protocolo que el [kernel](kernel-worklog.md): spec por tarea → tests de aceptación antes de implementar → implementación → decisiones aquí → commit atómico a `develop`.

Decisión de alcance (2026-08-04): la evaluación emparejada con/sin grafo (§14 de la visión) **no se ejecuta**. La justificación primaria de la característica es la comprensión humana del diseño: participar gráficamente en la arquitectura en lugar de solo en prosa. El anillo 1 entrega exactamente esa experiencia.

## 1. Backlog del anillo

| Tarea | Título | Alcance | Estado |
|---|---|---|---|
| A0 | Setup del anillo + cierre de deuda del kernel (CP-3, CP-4) | Este worklog; fallback de firma en commits del harness; derivación de locator en el compilador | ✅ hecho |
| A1 | Puerto `EventPublisher` + tabla de eventos | Eventos tipados append-only en SQLite con correlación misión/snapshot/tarea; los puntos que hoy notifican también publican | ✅ hecho |
| A2 | Emisión incremental del puerto del agente | Progreso de tools y fases como eventos en streaming | ✅ hecho |
| A3 | Servidor HTTP local de lectura | `127.0.0.1` + token por sesión + validación de origen; contratos públicos: mapa, diff pendiente, snapshot, historial, eventos vía long-poll | ✅ hecho |
| A4 | Comandos por HTTP | `/approve`, `/reject`, `/abort` por el mismo gate de interacciones tipadas que stdin/Telegram | ✅ hecho |
| A5 | UI de lectura | Grafo SVG (niveles e intents), zoom/pan, panel de diff con aprobar/rechazar, historial, feed de eventos | ✅ hecho |
| A6 | Checkpoint: misión real aprobada desde la UI | Validación de punta a punta en navegador | ✅ hecho |

Restricciones heredadas de la visión: la UI consume contratos públicos del núcleo (nunca SQLite directo); prototipo ligero sin cadena de frontend (librería de grafos madura solo si la edición lo exige); todo anillo conserva el modo headless.

## 2. Decisiones

### A0 — Setup + deuda del kernel

**D-A0.1 · CP-3: fallback de firma, no política propia.** El harness no puede custodiar claves del usuario, pero tampoco debe desactivar la firma en repos donde sí funciona. `final_commit` y el commit de merge intentan primero el commit normal (respetando `commit.gpgsign`); solo si git falla con un error de firma se reintenta con `-c commit.gpgsign=false`. El commit del harness es de automatización en rama de trabajo; el humano puede firmar al integrar. El reintento queda visible en el log del subproceso, no silenciado.

**D-A0.2 · CP-4: el compilador deriva el locator de CREATEs, no lo inventa.** Si un nodo CREATE llega sin `locator` pero su `label` parece una ruta de repositorio (contiene `/`, sin espacios, con extensión y miembro opcional `:Nombre`), el compilador usa el label como locator esperado. Solo aplica a CREATE: en CHANGE/REMOVE la ausencia de locator sigue siendo un issue, porque derivarlo enmascararía anclas rotas sobre código que debe existir. Con locator derivado, la reconciliación de K9 puede verificar la materialización (evita el `unverifiable` del hallazgo CP-4).

### A1 — Puerto `EventPublisher` + tabla de eventos ([spec](specs/A1-events.md))

**D-A1.1 · Puentes decoradores en vez de tocar call-sites.** `PublishingNotifier` y `PublishingLogger` envuelven los puertos existentes en la raíz de composición: toda notificación humana y toda métrica estructurada se convierte en evento sin modificar un solo punto de emisión. Cuando A2 añada emisión incremental explícita, los puntos nuevos publicarán directo al puerto; los puentes son la cobertura retroactiva, no el patrón final.

**D-A1.2 · El almacén asigna los ids, el emisor no correlaciona.** `event_id` es autoincremental de SQLite (monótono por misión) y la correlación `task_id`/`snapshot_id` se extrae del payload cuando existe. Los emisores no cambian su contrato: siguen publicando dicts planos, exactamente los que ya escribían en `_metrics.jsonl`.

**D-A1.3 · `publish` nunca mata la misión.** Mismo contrato de resiliencia que el logger de fichero: errores del almacén de eventos (disco, serialización) se tragan; además los puentes protegen con su propio try/except para publishers arbitrarios. Un fallo de telemetría no puede costar una misión con horas de trabajo.

**D-A1.4 · Conexión SQLite por operación.** Listeners (stdin/Telegram) y orquestador viven en hilos distintos; abrir-escribir-cerrar por evento evita conexiones compartidas entre hilos y mantiene el fichero utilizable por lectores externos (el servidor de A3 leerá el mismo `events.db`).

**D-A1.5 · `AppServices` sin campo nuevo hasta A3.** Ningún servicio de aplicación consume eventos aún; añadir el campo ahora sería un puerto muerto. Se añade cuando el servidor lea `events_since`. _Superada en A2: `PhaseExecutor` publica directamente, el campo llegó una tarea antes de lo previsto y con consumidor real._

### A2 — Emisión incremental del progreso del agente ([spec](specs/A2-agent-progress.md))

**D-A2.1 · Ciclo de vida de fase como eventos propios, sin fusionar con la métrica.** `phase_started`/`phase_ended` son eventos de ciclo de vida (incluyen bloqueos con su causa); la métrica `phase` de tokens/duración sigue existíendo tal cual. Fusionarlos habría roto el contrato de `_metrics.jsonl` que K10 fijó.

**D-A2.2 · `phase_ended` se emite en todas las salidas.** El helper `_blocked` del executor garantiza que timeout, max_turns, api_retries y gate_fail publican el cierre de fase con `block_kind` antes de devolver el bloqueo: la UI nunca verá una fase abierta para siempre.

**D-A2.3 · Un solo texto para log y evento.** `describe_tool_call` sale del logger de fichero como función de módulo y la comparten logger y puente: el resumen que se lee en `mission.log` es idéntico al del evento `tool_call`.

**D-A2.4 · Default nulo en `AppServices.events`.** `NullEventPublisher` (patrón `NoopCodeGraphService`) mantiene todas las fixtures existentes sin cambios; solo la composición real inyecta el almacén SQLite.

### A3 — Servidor HTTP local de lectura ([spec](specs/A3-web-server.md))

**D-A3.1 · Long-poll en vez de SSE.** §10 sanciona explícitamente el long polling para el MVP; con stdlib es trivial, testeable y sin conexiones persistentes que gestionar. `GET /api/events?after=N&wait=S` bloquea hasta 30 s. SSE/WebSocket solo con necesidad demostrada.

**D-A3.2 · El servidor compone adaptadores, el navegador ve contratos.** `MissionWebServer` reutiliza `DesignStore`, `SqliteEventLog` y `render_map_diff` — el mismo texto de diff que ve stdin/Telegram —; la UI nunca toca SQLite. Adaptadores frescos por petición: cada worker thread de `ThreadingHTTPServer` abre su propia conexión (coherente con D-A1.4).

**D-A3.3 · Seguridad mínima completa de §10.** Bind exclusivo a `127.0.0.1`, token `secrets.token_urlsafe` por sesión (header Bearer o query), y rechazo de `Origin` con host ajeno (bloquea que una web remota use el navegador del usuario como proxy hacia el servidor local). Sin endpoints que reciban rutas de filesystem: la política de rutas de §10 no aplica todavía.

**D-A3.4 · `--web` opcional, headless intacto.** El servidor solo arranca con el flag; corre como hilo daemon y no impide la salida del proceso. Sin `--web`, la misión es byte a byte la de antes.

### A4 — Comandos por HTTP ([spec](specs/A4-web-commands.md))

**D-A4.1 · Un solo gate para tres transportes.** `POST /api/command` recibe el texto crudo (`/approve`, `/reject <razón>`, respuesta plana) y lo pasa por `parse_control_command` — exactamente la misma función que stdin y Telegram — antes de publicar en el mismo `CommandBus`. Cero lógica nueva de interpretación: la web no puede divergir de los otros canales ni en un edge case.

**D-A4.2 · El servidor sin bus es de solo lectura explícita.** `commands` es opcional; sin él, `/api/command` responde `503`. Permite servir el estado de una misión terminada (inspección post-mortem) sin fingir que se puede interactuar.

### A5 — UI de lectura ([spec](specs/A5-read-ui.md))

**D-A5.1 · Un fichero, cero dependencias.** `static/index.html` con HTML+CSS+JS inline: sin npm, sin CDN, funciona offline y se sirve tal cual. Exactamente el "prototipo ligero" de §10; la librería de grafos madura queda condicionada a que los gestos de edición del anillo 2 lo desborden.

**D-A5.2 · Layout por carriles de nivel, no force-directed.** SYSTEM/PACKAGE/CODE como filas fijas: el eje vertical significa nivel de abstracción, que es la semántica del modelo, y el render es determinista (mismo mapa → misma imagen). Un layout físico aleatorio habría sido más vistoso y menos legible. Jerarquía por `parent_id` diferida a que un mapa real la pida.

**D-A5.3 · Reactividad por eventos, no por timer.** La UI refresca mapa/diff/snapshot solo cuando el long-poll de A3 entrega eventos nuevos; sin actividad no hay tráfico. El feed muestra el pulso de A2 (fases, tools, notificaciones) con el mismo texto del log.

**D-A5.4 · Validación visual en navegador real antes del commit.** Servidor de demo sembrado + Playwright: render de carriles/intents/edges verificado por captura, botón Approve verificado contra `/api/command` (200, `kind=approve`). Hallazgo corregido en el acto: cliente que recarga durante un long-poll producía `ConnectionAbortedError` ruidoso en el servidor → silenciado como desconexión normal.

### A6 — Checkpoint del anillo: misión real aprobada desde la UI (2026-08-04, ✅ aprobado)

Misión `focused --web` sobre COPILOT_LEARNING (`feature/case-index-v3`), operada íntegramente desde el navegador y abortada tras validar el circuito web para ahorrar tokens (el pipeline de ejecución ya se validó en el checkpoint 2 del kernel).

1. **A2 en producción** — El feed mostró en vivo cada tool del researcher (`find`, `GraphQuery`, lecturas, 9 `GraphPropose`) y los `phase_started/phase_ended` de research/structure/spec.
2. **A5 reactiva** — Al terminar research, el mapa real apareció en el lienzo sin recargar: 7 nodos en carriles (CREATE verde `tools/case_index.py`, CHANGE ámbar `INDEX.md`, 5 KEEP), edges `generates`/`reads`, diff coloreado idéntico al de stdin.
3. **A4 real** — Approve pulsado en el navegador → snapshot `9187e49e210c`, changeset compilado, fase structure arrancada. Abort vía `POST /api/command` → misión cerró limpia en el límite de fase (`BLOCKED | user_abort`, reporte generado).
4. **CP-4 confirmado en producción** — El researcher puso `locator` al nodo CREATE tras la mitigación del schema: el diff mostró `(tools/case_index.py)` y la materialización sería verificable.
5. **Historial útil** — La UI expuso los intentos CAS del researcher (5 REJECTED por validación/conflicto, 4 APPLIED): el modo por turnos es visible y auditable.

**Hallazgo A6-1 · `prompt()` no existe en navegadores embebidos.** Reject/Abort fallaban en silencio en el navegador integrado de VS Code. Corregido: fallback al campo de respuesta como fuente de la razón cuando `prompt()` lanza.

**Hallazgo A6-2 · Flaky de la suite cazado.** Los POSTs rechazados (401/403) respondían sin drenar el body pendiente y Windows abortaba la conexión (`WinError 10053`) intermitentemente. Corregido: el handler lee el body antes de responder. Tres pasadas verdes consecutivas (123/123).

**🏁 Anillo 1 completo (A0–A6).** El pizarrón vive en el navegador: mapa, diff, aprobación, pulso del agente e historial, sin sacrificar el modo headless. Siguiente anillo según §12: edición manual desde el lienzo.

## 3. Auditoría

| Tarea | Tests de aceptación | Suite | Desviaciones de spec | Veredicto |
|---|---|---|---|---|
| A0 | 3/3 CP-4 (tests/domain/test_changeset.py C9–C11) + 2/2 CP-3 (tests/adapters/test_git_service.py) | 91/91 verde | Sin spec formal: tarea de deuda, decisiones D-A0.1/D-A0.2 documentadas aquí | ✅ |
| A1 | 8/8 (tests/adapters/test_event_log.py): E1–E7 de la spec; E8 = suite previa | 99/99 verde | `AppServices` sin campo `events` hasta A3 (D-A1.5), declarado en spec §2.5 | ✅ |
| A2 | 6/6 (tests/application/test_agent_progress.py): P1–P5; P6 = suite previa | 105/105 verde | D-A1.5 superada (campo `events` añadido en A2 con consumidor real); test E6 de A1 actualizado al nuevo contrato de `tool_call` | ✅ |
| A3 | 8/8 (tests/adapters/test_web_server.py): W1–W7; W8 = suite previa | 113/113 verde | SSE del backlog sustituido por long-poll (D-A3.1, sancionado por §10) | ✅ |
| A4 | 6/6 (tests/adapters/test_web_commands.py): C1–C6; C7 = suite previa | 119/119 verde | Ninguna: diff limitado a server.py, cli.py, spec, tests y worklog | ✅ |
| A5 | 4/4 (tests/adapters/test_read_ui.py): U1–U4; U5 = suite previa + validación visual en navegador (D-A5.4) | 123/123 verde | Namespace SVG de w3.org excluido del chequeo de recursos externos (identificador XML, no recurso); fix de conexiones abortadas en long-poll | ✅ |
| A6 | Misión real operada desde el navegador (mapa en vivo, approve, abort) | 123/123 verde ×3 pasadas | Hallazgos A6-1 (`prompt()` embebido → fallback) y A6-2 (drenaje de body en POSTs rechazados → flaky resuelto) corregidos en el propio checkpoint | ✅ |
