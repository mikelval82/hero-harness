# HERO v2 — Anillo 1 "El mapa visible": estructura de trabajo y auditoría

Cuaderno de trabajo del primer anillo posterior al kernel, descrito en [hero-v2-grafo-vivo.md](../hero-v2-grafo-vivo.md) (secciones 10 y 12). Mismo protocolo que el [kernel](kernel-worklog.md): spec por tarea → tests de aceptación antes de implementar → implementación → decisiones aquí → commit atómico a `develop`.

Decisión de alcance (2026-08-04): la evaluación emparejada con/sin grafo (§14 de la visión) **no se ejecuta**. La justificación primaria de la característica es la comprensión humana del diseño: participar gráficamente en la arquitectura en lugar de solo en prosa. El anillo 1 entrega exactamente esa experiencia.

## 1. Backlog del anillo

| Tarea | Título | Alcance | Estado |
|---|---|---|---|
| A0 | Setup del anillo + cierre de deuda del kernel (CP-3, CP-4) | Este worklog; fallback de firma en commits del harness; derivación de locator en el compilador | ✅ hecho |
| A1 | Puerto `EventPublisher` + tabla de eventos | Eventos tipados append-only en SQLite con correlación misión/snapshot/tarea; los puntos que hoy notifican también publican | ⬜ |
| A2 | Emisión incremental del puerto del agente | Progreso de tools y fases como eventos en streaming | ⬜ |
| A3 | Servidor HTTP local de lectura | `127.0.0.1` + token por sesión + validación de origen; contratos públicos: mapa, diff pendiente, snapshot, historial, eventos vía SSE | ⬜ |
| A4 | Comandos por HTTP | `/approve`, `/reject`, `/abort` por el mismo gate de interacciones tipadas que stdin/Telegram | ⬜ |
| A5 | UI de lectura | Grafo SVG (niveles e intents), zoom/pan, panel de diff con aprobar/rechazar, historial, feed de eventos | ⬜ |
| A6 | Checkpoint: misión real aprobada desde la UI | Validación de punta a punta en navegador | ⬜ |

Restricciones heredadas de la visión: la UI consume contratos públicos del núcleo (nunca SQLite directo); prototipo ligero sin cadena de frontend (librería de grafos madura solo si la edición lo exige); todo anillo conserva el modo headless.

## 2. Decisiones

### A0 — Setup + deuda del kernel

**D-A0.1 · CP-3: fallback de firma, no política propia.** El harness no puede custodiar claves del usuario, pero tampoco debe desactivar la firma en repos donde sí funciona. `final_commit` y el commit de merge intentan primero el commit normal (respetando `commit.gpgsign`); solo si git falla con un error de firma se reintenta con `-c commit.gpgsign=false`. El commit del harness es de automatización en rama de trabajo; el humano puede firmar al integrar. El reintento queda visible en el log del subproceso, no silenciado.

**D-A0.2 · CP-4: el compilador deriva el locator de CREATEs, no lo inventa.** Si un nodo CREATE llega sin `locator` pero su `label` parece una ruta de repositorio (contiene `/`, sin espacios, con extensión y miembro opcional `:Nombre`), el compilador usa el label como locator esperado. Solo aplica a CREATE: en CHANGE/REMOVE la ausencia de locator sigue siendo un issue, porque derivarlo enmascararía anclas rotas sobre código que debe existir. Con locator derivado, la reconciliación de K9 puede verificar la materialización (evita el `unverifiable` del hallazgo CP-4).

## 3. Auditoría

| Tarea | Tests de aceptación | Suite | Desviaciones de spec | Veredicto |
|---|---|---|---|---|
| A0 | 3/3 CP-4 (tests/domain/test_changeset.py C9–C11) + 2/2 CP-3 (tests/adapters/test_git_service.py) | 91/91 verde | Sin spec formal: tarea de deuda, decisiones D-A0.1/D-A0.2 documentadas aquí | ✅ |
