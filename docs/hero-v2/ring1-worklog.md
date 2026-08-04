# HERO v2 — Anillo 1 "El mapa visible": estructura de trabajo y auditoría

Cuaderno de trabajo del primer anillo posterior al kernel, descrito en [hero-v2-grafo-vivo.md](../hero-v2-grafo-vivo.md) (secciones 10 y 12). Mismo protocolo que el [kernel](kernel-worklog.md): spec por tarea → tests de aceptación antes de implementar → implementación → decisiones aquí → commit atómico a `develop`.

Decisión de alcance (2026-08-04): la evaluación emparejada con/sin grafo (§14 de la visión) **no se ejecuta**. La justificación primaria de la característica es la comprensión humana del diseño: participar gráficamente en la arquitectura en lugar de solo en prosa. El anillo 1 entrega exactamente esa experiencia.

## 1. Backlog del anillo

| Tarea | Título | Alcance | Estado |
|---|---|---|---|
| A0 | Setup del anillo + cierre de deuda del kernel (CP-3, CP-4) | Este worklog; fallback de firma en commits del harness; derivación de locator en el compilador | ✅ hecho |
| A1 | Puerto `EventPublisher` + tabla de eventos | Eventos tipados append-only en SQLite con correlación misión/snapshot/tarea; los puntos que hoy notifican también publican | ✅ hecho |
| A2 | Emisión incremental del puerto del agente | Progreso de tools y fases como eventos en streaming | ✅ hecho |
| A3 | Servidor HTTP local de lectura | `127.0.0.1` + token por sesión + validación de origen; contratos públicos: mapa, diff pendiente, snapshot, historial, eventos vía SSE | ⬜ |
| A4 | Comandos por HTTP | `/approve`, `/reject`, `/abort` por el mismo gate de interacciones tipadas que stdin/Telegram | ⬜ |
| A5 | UI de lectura | Grafo SVG (niveles e intents), zoom/pan, panel de diff con aprobar/rechazar, historial, feed de eventos | ⬜ |
| A6 | Checkpoint: misión real aprobada desde la UI | Validación de punta a punta en navegador | ⬜ |

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

## 3. Auditoría

| Tarea | Tests de aceptación | Suite | Desviaciones de spec | Veredicto |
|---|---|---|---|---|
| A0 | 3/3 CP-4 (tests/domain/test_changeset.py C9–C11) + 2/2 CP-3 (tests/adapters/test_git_service.py) | 91/91 verde | Sin spec formal: tarea de deuda, decisiones D-A0.1/D-A0.2 documentadas aquí | ✅ |
| A1 | 8/8 (tests/adapters/test_event_log.py): E1–E7 de la spec; E8 = suite previa | 99/99 verde | `AppServices` sin campo `events` hasta A3 (D-A1.5), declarado en spec §2.5 | ✅ |
| A2 | 6/6 (tests/application/test_agent_progress.py): P1–P5; P6 = suite previa | 105/105 verde | D-A1.5 superada (campo `events` añadido en A2 con consumidor real); test E6 de A1 actualizado al nuevo contrato de `tool_call` | ✅ |
