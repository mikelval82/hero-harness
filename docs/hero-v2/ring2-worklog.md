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
| B3 | Gestos de creación | Crear nodo (doble click en carril), dibujar edge (arrastre nodo→nodo), marcar REMOVE | ⬜ |
| B4 | Conflictos CAS en la UI | Revisión movida durante la edición → refetch + aviso, nunca sobrescritura silenciosa | ⬜ |
| B5 | Checkpoint: mapa dibujado a mano | Ajustar el mapa en el navegador, aprobar y compilar changeset de él | ⬜ |

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

## 3. Auditoría

| Tarea | Tests de aceptación | Suite | Desviaciones de spec | Veredicto |
|---|---|---|---|---|
| B1 | 9/9 (tests/adapters/test_design_propose.py): G1–G7 + G1b; G8 = suite previa | 131/131 verde | Ninguna: diff limitado a server.py, spec, tests y worklog | ✅ |
| B2 | 2/2 (tests/adapters/test_node_inspector.py): I1–I2; I3 = suite previa; I4 = navegador real (D-B2.3) | 133/133 verde | Ninguna: diff limitado a index.html, spec, tests y worklog | ✅ |
