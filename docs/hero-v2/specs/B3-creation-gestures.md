# B3 — Gestos de creación en el lienzo

Spec completa (es la tarea que decide si el prototipo SVG aguanta la edición). Anillo 2, tarea B3. Referencia: visión §12 ("la edición manual desde el lienzo con los gestos como operaciones normales") y §10 (si selección/conexiones/undo crecen, librería madura como dependencia opcional).

## 1. Problema

Con B2 se corrige lo que existe; falta poder **añadir** al pizarrón: un nodo que el researcher no propuso, una relación que falta, quitar lo que sobra. Los gestos deben producir operaciones normales (`add_node`, `add_edge`, `remove_node`, `remove_edge`) por B1 — nada de estado local que luego "se sincronice".

## 2. Contrato

### 2.1 Gestos

| Gesto | Operación | Detalle |
|---|---|---|
| **Doble click en un carril** | `add_node` | El carril bajo el cursor fija el `level` (los tres carriles se dibujan siempre, aunque estén vacíos). Inspector en modo creación: `id` (auto-slug del label, editable), label, intent (default CREATE), locator, description. `provenance=HUMAN`, `location=IN_REPOSITORY` |
| **Shift+arrastre de nodo a nodo** | `add_edge` | Línea fantasma siguiendo el cursor; al soltar sobre otro nodo, inspector en modo edge: `source → target` fijos, campo `relation`. `provenance=HUMAN`, `intent=CREATE` |
| **Click en un edge** | — | Inspector de edge (source/target/relation/intent, solo lectura) con botón de borrado |
| **Botón Delete en el inspector** | `remove_node` / `remove_edge` | Confirmación en dos clicks (el primero arma, el segundo envía); sin `prompt()` (A6-1) |

- Todos los gestos envían por `POST /api/design/propose` con la `base_revision` cargada; el resultado (`APPLIED`/`CONFLICT`/`REJECTED` + detail) se muestra en el inspector, como en B2.
- Shift+arrastre no inicia pan; el pan normal no cambia.
- El inspector es multimodo (nodo / nodo nuevo / edge nuevo / edge): los campos irrelevantes se ocultan por modo.

### 2.2 Validación delegada

El cliente no re-valida: ids duplicados, endpoints inexistentes, edges duplicados y enums inválidos los rechaza el store de K4 y el inspector muestra el `detail`. Única lógica de cliente: el auto-slug del id y el diff de campos (B2).

## 3. Criterios de aceptación

Automatizables (HTML servido):

- **H1** El inspector multimodo existe: campos `insp-id` y `insp-relation`, botón `insp-delete`; el JS contiene las cuatro operaciones (`add_node`, `add_edge`, `remove_node`, `remove_edge`).
- **H2** Los gestos están cableados: handler de `dblclick` con derivación de carril (`laneFromY`), arrastre de edge con Shift (`edgeDrag`), y los tres carriles se renderizan siempre.
- **H3** La suite previa (133 tests) permanece verde.

En navegador real (protocolo D-A5.4), pre-commit:

- **H4** Doble click en CODE → crear nodo → APPLIED y renderizado en el carril CODE con historial HUMAN.
- **H5** Shift+arrastre entre dos nodos → relation → APPLIED y edge dibujado.
- **H6** Delete de un edge y de un nodo → desaparecen del lienzo (cascada del store para edges del nodo).
- **H7** Veredicto sobre la condición D-A5.1: ¿aguanta el SVG artesanal o se adopta Cytoscape?

## 4. Fuera de alcance

- Editar `relation` de un edge existente (borrar y recrear cubre el caso en v1).
- Undo (mecanismo diferido de §12), multi-selección, `parent_id` visual.
- Manejo fino de CONFLICT (B4).
