# HERO v2 — Anillo 2 "El lienzo editable": estructura de trabajo y auditoría

Cuaderno de trabajo del segundo anillo, descrito en [hero-v2-grafo-vivo.md](../hero-v2-grafo-vivo.md) (§12: "la edición manual desde el lienzo con los gestos como operaciones normales"; §11: la flecha de operaciones de diseño desde el humano). Mismo protocolo que el [kernel](kernel-worklog.md) y el [anillo 1](ring1-worklog.md): spec por tarea → tests de aceptación antes de implementar → implementación → decisiones aquí → commit atómico a `develop`.

Principio rector del anillo: **el humano no tiene camino privilegiado**. Sus gestos entran por el mismo `DesignStore.apply` (CAS, validación, historial) que las propuestas de los agentes, con `author=HUMAN`. El anillo es transporte e interacción; no hay lógica nueva de dominio.

Decisión de alcance (2026-08-04): Mermaid descartado como motor del lienzo (compilador texto→imagen, no editable); queda como posible exportación futura mapa→texto.

## 1. Backlog del anillo

| Tarea | Título | Alcance | Estado |
|---|---|---|---|
| B0 | Setup del anillo | Este worklog | ✅ hecho |
| B1 | `POST /api/design/propose` | Operaciones de diseño humanas por el mismo CAS que los agentes, con evento publicado | ✅ hecho |
| B2 | Inspector de nodos en la UI | Click → panel de campos; editar label/intent/descripción/locator vía B1 | ✅ hecho |
| B3 | Gestos de creación | Crear nodo (doble click en carril), dibujar edge (arrastre nodo→nodo), marcar REMOVE | ✅ hecho |
| B4 | Conflictos CAS en la UI | Revisión movida durante la edición → refetch + aviso, nunca sobrescritura silenciosa | ✅ hecho |
| B5 | Checkpoint: mapa dibujado a mano | Ajustar el mapa en el navegador, aprobar y compilar changeset de él | ✅ hecho |

En B3 se evalúa la condición de D-A5.1: si los gestos desbordan el SVG artesanal, se adopta una librería de grafos madura (Cytoscape.js) como dependencia opcional del adaptador web.

## 2. Decisiones

### B1 — Operaciones de diseño humanas por HTTP ([spec](specs/B1-design-propose.md))

**D-B1.1 · El transporte no traduce.** La respuesta expone el vocabulario exacto de `ApplyStatus` (`APPLIED`/`CONFLICT`/`REJECTED`/`DUPLICATE`) con `200` siempre que la petición sea bien formada. La UI (B4) decidirá cómo reaccionar; mapear estados a códigos HTTP habría creado una segunda semántica que mantener sincronizada con la del `GraphPropose` de los agentes.

**D-B1.2 · `operation_id` generado en servidor si falta.** La idempotencia de K4 exige un id; para gestos espontáneos de UI el servidor genera `human-<uuid8>`. Si el cliente lo envía (reintentos deliberados), se respeta.

**D-B1.3 · Sin dependencia del `CommandBus`.** Editar el diseño de una misión parada es legítimo (preparar el mapa antes de relanzar); el endpoint funciona en el servidor de solo lectura post-mortem.

**D-B1.4 · El evento `design_proposal` cierra el bucle reactivo.** Publicado en `events.db`, cualquier vista abierta refresca por el long-poll de A3: las ediciones humanas se propagan a otras pestañas (y al feed) sin código nuevo de sincronización.

### B2 — Inspector de nodos ([spec](specs/B2-node-inspector.md))

**D-B2.1 · Solo los campos modificados viajan.** `changedFields` calcula el diff entre el formulario y el nodo cargado; guardar sin cambios cierra sin tráfico. Un `update_node` con todos los campos habría pisado ediciones concurrentes que el CAS no detecta (misma revisión, campos distintos).

**D-B2.2 · Nivel y procedencia no se editan desde el inspector.** `level` cambia la semántica espacial del nodo y `provenance` es un hecho histórico, no una opinión editable. El subconjunto útil es label/intent/locator/description; el resto queda en la línea de metadatos de solo lectura.

**D-B2.3 · Validación en navegador antes del commit (protocolo D-A5.4).** Demo sembrada: click en nodo → inspector con valores; editar label+locator → APPLIED, revisión 1→2, lienzo re-renderizado con el nuevo label y locator en el tooltip/diff, historial `human-… (HUMAN, base 1)`, evento `design_proposal` en el feed. El bucle reactivo de D-B1.4 confirmado: el refresh llegó por el long-poll, no por lógica ad-hoc.

### B3 — Gestos de creación ([spec](specs/B3-creation-gestures.md))

**D-B3.1 · Inspector multimodo, no cuatro paneles.** Un solo panel con visibilidad de filas por modo (nodo / nodo nuevo / edge nuevo / edge): los cuatro gestos comparten guardado, borrado y línea de estado. Cuatro paneles habrían cuadruplicado el manejo de resultados de B1.

**D-B3.2 · Los tres carriles se dibujan siempre.** Un carril vacío debe aceptar doble click (crear el primer nodo SYSTEM de un mapa vacío); además estabiliza la geometría: `laneFromY` elige el carril más cercano al cursor.

**D-B3.3 · Validación delegada al store.** El cliente solo hace auto-slug del id y diff de campos; duplicados, endpoints inexistentes y enums inválidos los rechaza K4 y el inspector muestra el `detail`. Cero reglas duplicadas entre cliente y dominio.

**D-B3.4 · Borrado en dos clicks, sin `prompt()`.** El botón se arma ("Confirm delete") y el segundo click envía — compatible con navegadores embebidos (hallazgo A6-1).

**D-B3.5 · Veredicto D-A5.1 (H7): el SVG artesanal aguanta.** Los cuatro gestos (crear nodo, arrastre de edge con línea fantasma, borrar nodo/edge, editar) funcionan con ~120 líneas de JS sin librería. Cytoscape queda diferido hasta que aparezca una necesidad que lo justifique (multi-selección, layout automático de mapas grandes, undo visual).

**Validación en navegador (H4–H6):** doble click en CODE → `metrics-reporter` creado con auto-slug, `HUMAN`, renderizado en su carril (rev 1→2); shift+arrastre cache→metrics-reporter → edge `reports` (rev 2→3); borrado de edge y nodo con confirmación doble (rev 3→5, cascada del store verificada). Historial completo `human-…` en la UI.

### B4 — Conflictos CAS en la UI ([spec](specs/B4-cas-conflicts.md))

**D-B4.1 · El conflicto recarga, el humano reintenta.** En `CONFLICT` la UI hace refresh automático (el humano ve la verdad que ganó) pero **nunca** reintenta la operación sola: los valores tecleados persisten y el segundo Save es una decisión deliberada contra la revisión nueva. Reintentar automáticamente habría convertido el CAS en un last-writer-wins disfrazado.

**D-B4.2 · Re-vinculación en cada refresh.** `rebindInspector` apunta el inspector a la instancia fresca del nodo tras cualquier refresh (conflicto o long-poll de fondo): el diff de campos de D-B2.1 se calcula siempre contra la verdad actual. Si el objetivo desapareció, el Save queda inerte y se avisa.

**Validación en navegador (J3):** con el inspector abierto y label editado, una escritura fuera de banda movió la revisión 1→2; Save → `CONFLICT: map reloaded at revision 2`, valores intactos, nodo intruso visible en el lienzo; segundo Save → APPLIED (rev 3). El historial del store registra la secuencia íntegra: `#3 CONFLICT (base 1)` → `#4 APPLIED (base 2)`.

### B5 — Checkpoint del anillo: mapa co-diseñado por humano y agente (2026-08-04, ✅ aprobado)

Misión `focused --web` real sobre COPILOT_LEARNING (`feature/case-index-v5`), abortada tras structure para ahorrar tokens. El researcher propuso su mapa (rev 2) y el humano lo **co-diseñó desde el navegador** antes de aprobar:

1. **Edición** — descripción del CREATE del agente refinada vía inspector (`Entries sorted alphabetically by title`, rev 3).
2. **Creación** — nodo `tools-test-case-index-py` dibujado con doble click en CODE (locator incluido, rev 4) y edge `verifies` con shift+arrastre (rev 5).
3. **CAS de aprobación en producción** — el primer Approve chocó con la revisión movida por el propio edge: el coordinador K5 lo rechazó ("the map changed while waiting") y re-mostró el diff completo de rev 5. Segundo Approve → snapshot `2bbb17a1452d`. Nadie aprueba lo que no ha visto.
4. **Artefactos verificados** — `approved_snapshot.json`: 6 nodos con el humano dentro (`tools-test-case-index-py · HUMAN · CREATE`) y el edge `verifies`. `changeset.json`: 5 operaciones, **cero issues**, incluyendo `create:tools-test-case-index-py`. Y el remate: el structurer generó **`task-2` desde el nodo dibujado a mano** — el gesto del humano se volvió tarea ejecutable por el mismo camino que las propuestas del agente.

Abort limpio vía web (`BLOCKED | user_abort`), repo de prueba restaurado.

**🏁 Anillo 2 completo (B0–B5).** El pizarrón es de verdad compartido: humano y agentes dibujan sobre el mismo grafo, con las mismas reglas, el mismo CAS y el mismo historial. La visión de §7 — colaborar en el diseño, no aprobar prosa — está operativa de punta a punta.

## 3. Auditoría

| Tarea | Tests de aceptación | Suite | Desviaciones de spec | Veredicto |
|---|---|---|---|---|
| B1 | 9/9 (tests/adapters/test_design_propose.py): G1–G7 + G1b; G8 = suite previa | 131/131 verde | Ninguna: diff limitado a server.py, spec, tests y worklog | ✅ |
| B2 | 2/2 (tests/adapters/test_node_inspector.py): I1–I2; I3 = suite previa; I4 = navegador real (D-B2.3) | 133/133 verde | Ninguna: diff limitado a index.html, spec, tests y worklog | ✅ |
| B3 | 2/2 (tests/adapters/test_creation_gestures.py): H1–H2; H3 = suite previa; H4–H7 = navegador real (D-B3.5) | 135/135 verde | Ninguna: diff limitado a index.html, spec, tests y worklog | ✅ |
| B4 | 1/1 (tests/adapters/test_cas_conflicts.py): J1; J2 = suite previa; J3 = navegador real (conflicto fuera de banda) | 136/136 verde | Ninguna: diff limitado a index.html, spec, tests y worklog | ✅ |
| B5 | Misión real: mapa del researcher co-editado desde el navegador (update+create+edge), aprobado y compilado con las ediciones humanas dentro | 136/136 verde | Sin código nuevo: checkpoint de validación; CAS de aprobación K5 verificado en producción | ✅ |
