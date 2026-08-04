# B4 — Conflictos CAS en la UI

Spec ligera. Anillo 2, tarea B4. Referencia: visión §7 (modo por turnos: humano y agentes sobre el mismo grafo sin pisarse) y K5 (CAS como única regla de concurrencia).

## 1. Problema

Mientras editas en el inspector, el researcher (u otra pestaña) puede mover la revisión. El CAS de K4 ya impide la sobrescritura — la propuesta vuelve `CONFLICT` — pero la UI de B2/B3 solo muestra el estado: el humano queda con un formulario relleno, un mapa desactualizado y sin camino claro. B4 convierte el conflicto en un flujo: recargar, enseñar la verdad nueva y dejar que el humano reintente **deliberadamente**.

## 2. Contrato

- **En `CONFLICT`**: la UI recarga el mapa automáticamente (revisión y lienzo al día), **conserva intactos los valores tecleados**, re-vincula el inspector al nodo fresco y muestra: `CONFLICT: map reloaded at revision N — review and Save to retry`. El siguiente Save usa la revisión nueva. Nunca hay reintento automático: el humano re-confirma viendo el mapa actualizado.
- **Si el objetivo desapareció** (el agente eliminó el nodo/edge): mensaje `no longer exists` y el Save queda inerte para ese objetivo.
- **Refresh de fondo** (long-poll mientras el inspector está abierto): re-vincula `inspector.node` a la instancia fresca para que el diff de campos (D-B2.1) se calcule contra la verdad actual; los valores del formulario no se tocan.
- Aplica a los cuatro modos del inspector (nodo, nodo nuevo, edge nuevo, edge).

## 3. Criterios de aceptación

Automatizables (HTML servido):

- **J1** El JS contiene el flujo de conflicto (`map reloaded`, re-vinculación del nodo tras refresh, `no longer exists`).
- **J2** La suite previa (135 tests) permanece verde.

En navegador real (protocolo D-A5.4), pre-commit:

- **J3** Con el inspector abierto y edición a medias, una escritura fuera de banda mueve la revisión → Save devuelve CONFLICT, el mapa se recarga a la revisión nueva, los valores tecleados persisten → segundo Save → APPLIED con la revisión fresca.

## 4. Fuera de alcance

- Merge de campos (si el agente cambió el mismo campo, gana el último Save humano deliberado — el humano ve el mapa nuevo antes de confirmar).
- Bloqueo por entidad (mecanismo diferido de §12).
