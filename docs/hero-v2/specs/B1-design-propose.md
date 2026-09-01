# B1 — Operaciones de diseño humanas por HTTP

Spec completa. Anillo 2, tarea B1. Referencia: visión §11 (la flecha "Design operations" del humano hacia el grafo de diseño corresponde al anillo de edición manual) y §7 (humano y agentes colaboran sobre el mismo grafo con las mismas reglas).

## 1. Problema

El humano puede ver el mapa (A5) y aprobar/rechazar (A4), pero no puede tocarlo: cualquier corrección — renombrar un nodo, cambiar un intent, añadir una relación que el researcher no vio — exige rechazar el mapa entero y pedirle al agente que lo redibuje. El anillo 2 empieza por el transporte: sus operaciones deben viajar al `DesignStore` con exactamente las mismas garantías que las de los agentes.

## 2. Contrato

### 2.1 Endpoint

`POST /api/design/propose`, cuerpo JSON:

```json
{
  "operation_id": "human-…"   // opcional: el servidor genera uno si falta
  "base_revision": 3,          // obligatorio: CAS contra la revisión actual
  "operations": [ { "op": "add_node", … } ]  // mismas operaciones que GraphPropose
}
```

- El servidor invoca `DesignStore.apply(operation_id, author="HUMAN", base_revision, operations)`. **Cero lógica nueva**: la validación (enums, campos, edges huérfanos), la atomicidad del batch, el CAS y el registro en historial son los de K4.
- Respuesta `200` con `{"status": "APPLIED"|"CONFLICT"|"REJECTED"|"DUPLICATE", "design_revision": <actual>, "detail": "…"}` — el mismo vocabulario que ve el agente en `GraphPropose`. La UI decide cómo reaccionar (B4); el transporte no traduce.
- Cuerpo malformado (JSON inválido, sin `base_revision`, `operations` no lista) → `400`.
- Seguridad idéntica a A3/A4 (token + origen). No depende del `CommandBus`: editar el diseño de una misión parada es legítimo.

### 2.2 Evento

Cada propuesta humana publica `design_proposal` en `events.db`: `{"operation_id", "author": "HUMAN", "status", "design_revision"}`. Efectos: el feed muestra la edición, y cualquier otra vista abierta refresca el mapa por el long-poll existente (la reactividad de A5 cubre las ediciones humanas gratis).

## 3. Criterios de aceptación

- **G1** `add_node` válido → `status=APPLIED`, `design_revision` incrementada; el nodo aparece en `/api/map` y la operación en `/api/history` con `author=HUMAN`.
- **G2** `base_revision` obsoleta → `status=CONFLICT`, mapa intacto.
- **G3** Operación inválida (campos faltantes) → `status=REJECTED`, revisión intacta, `detail` explica la causa.
- **G4** Reenvío del mismo `operation_id` → `status=DUPLICATE` (idempotencia de K4).
- **G5** Sin token → `401`; `Origin` ajeno → `403`; nada llega al store.
- **G6** Una propuesta aplicada publica el evento `design_proposal` con autor HUMAN.
- **G7** Cuerpo malformado → `400` sin tocar el store.
- **G8** La suite previa (123 tests) permanece verde.

## 4. Fuera de alcance

- Toda la interacción visual (B2–B4).
- Permisos por usuario: hay un solo humano por sesión de servidor (token único de A3).
