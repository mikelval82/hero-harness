# B2 — Inspector de nodos en la UI

Spec ligera (el transporte es B1; esto es interacción en el estático de A5). Anillo 2, tarea B2. Referencia: visión §7 (el humano corrige el diseño donde lo ve) y §10 (la UI añade edición tras el modo lectura).

## 1. Problema

El humano ve el mapa pero no puede corregirlo: un label pobre, un intent equivocado o un locator ausente exigen rechazar y pedir al agente que redibuje. B2 da la primera escritura desde el lienzo: seleccionar un nodo y editar sus campos mutables.

## 2. Contrato

- **Selección**: click en un nodo del SVG → panel inspector en el lateral con sus campos.
- **Campos editables**: `label`, `intent` (select con los 4 valores), `locator`, `description` — el subconjunto útil de `_UPDATABLE_NODE_FIELDS`. Solo lectura: `id`, `level`, `provenance`, `location` (nivel y procedencia no se cambian desde el inspector en v1; `remove_node` es gesto de B3).
- **Guardar**: envía a `POST /api/design/propose` una única operación `update_node` con **solo los campos modificados**, `base_revision` = la revisión del último `/api/map` cargado. Sin cambios → cierra sin tráfico.
- **Resultado**: el estado (`APPLIED`/`CONFLICT`/`REJECTED`) y el `detail` se muestran en el inspector; con `APPLIED` se refresca el mapa (y el evento `design_proposal` de B1 aparece en el feed). El tratamiento fino de CONFLICT (refetch automático + re-aplicación guiada) es B4.
- La UI sigue siendo un único `index.html` sin dependencias.

## 3. Criterios de aceptación

Automatizables (suite, sobre el HTML servido):

- **I1** El HTML contiene el inspector (panel, inputs de label/locator/description, select de intent, botones guardar/cerrar).
- **I2** El JS usa `update_node` y `/api/design/propose`, y solo envía campos modificados (marcador de la función de diff).
- **I3** La suite previa (131 tests) permanece verde.

En navegador real (validación pre-commit, protocolo D-A5.4):

- **I4** Click en nodo → inspector con sus valores; editar label → APPLIED → el lienzo re-renderiza con el nuevo label; `/api/history` registra la operación con `author=HUMAN`; el feed muestra `design_proposal`.

## 4. Fuera de alcance

- Crear/eliminar nodos y edges (B3).
- Resolución de conflictos CAS más allá de mostrar el estado (B4).
