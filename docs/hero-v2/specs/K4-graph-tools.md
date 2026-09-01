# K4 — Herramientas de grafo para agentes

Spec completa. Da manos a `researcher` y `griller` para leer y proponer sobre el mapa mediante tools validadas, en lugar de describirlo en markdown o improvisar SQL. Deriva de las secciones 5 y 7 de [hero-v2-grafo-vivo.md](../../hero-v2-grafo-vivo.md) y consume el contrato de K2.

## 1. Alcance

Entra: tools `GraphQuery` y `GraphPropose` en el `ToolRegistry`, activadas solo en las fases RESEARCH y GRILL, prompts de ambos agentes actualizados para que su producto sea mapa + documento.

No entra: aprobación (K5), compilación (K6), acceso de la UI (anillos), validación de locators contra path policy (se hace al compilar la tarea, K6, según la sección 10 de la visión — el locator aquí es un dato, no un acceso a fichero).

## 2. Decisiones de contrato

**Salida JSON compacto, siempre con `design_revision`.** Toda respuesta de `GraphQuery` y `GraphPropose` incluye la revisión vigente, porque el agente la necesita como `base_revision` de su siguiente propuesta. Sin ella el protocolo CAS obligaría a una llamada extra por turno.

**El autor de las operaciones es `AGENT`, fijado por la tool.** El agente no puede firmar como HUMAN ni ANALYZER: la procedencia la impone el canal, no el contenido. (La dimensión `provenance` de cada nodo propuesto sí la elige el agente, porque puede transcribir una decisión humana del chat.)

**Conflictos y rechazos son salida normal, no error de tool.** `GraphPropose` devuelve `CONFLICT`/`REJECTED` con detalle accionable (la revisión actual, el motivo de validación) en lugar de lanzar: el agente debe poder leer el resultado y reintentar razonadamente.

**`GraphQuery` cubre las dos capas.** `scope="design"` devuelve nodos (con resolución calculada contra hechos), aristas y revisión, filtrable por `level`/`parent_id`/`intent`; `scope="facts"` busca por patrón en los nodos observados (id/tipo/fichero) para que el agente ancle sus propuestas sin usar Bash.

**Ubicación de las bases.** `design.db` y `code_graph.db` en el `harness_dir` del `ToolEnvironment` (ámbito misión, coherente con K3: la propuesta editable pertenece a la misión).

## 3. Contrato de las tools

`GraphQuery` — input: `{scope: "design"|"facts", level?, parent_id?, intent?, pattern?}`. Output design: `{"design_revision": N, "nodes": [{id,label,level,provenance,location,intent,parent_id,locator,resolution}], "edges": [...]}`. Output facts: `{"design_revision": N, "matches": [{id,type,file}]}` (máx. 50).

`GraphPropose` — input: `{operation_id: str, base_revision: int, operations: [op...]}` con los tipos de operación de K2. Output: `{"status": "APPLIED"|"CONFLICT"|"REJECTED"|"DUPLICATE", "design_revision": N, "detail": str}`.

## 4. Tabla de aceptación

| # | Caso | Resultado esperado |
|---|------|--------------------|
| B1 | `GraphQuery` design sobre misión vacía | `design_revision: 0`, nodos y aristas vacíos |
| B2 | `GraphPropose` válido y luego `GraphQuery` | `APPLIED` con revisión 1; la consulta devuelve los nodos con `resolution` calculada contra hechos (RESOLVED si el locator existe, UNRESOLVED si no, EXTERNAL por ubicación) |
| B3 | `GraphPropose` con `base_revision` obsoleta | `CONFLICT`, `design_revision` refleja la actual, nada aplicado |
| B4 | `GraphPropose` con operación inválida | `REJECTED` con detalle, nada aplicado |
| B5 | Reenvío del mismo `operation_id` | `DUPLICATE` con la revisión original |
| B6 | `GraphQuery` facts con patrón | matches con id/type/file desde el grafo observado |
| B7 | Registro y fases | ambas tools en `default_tool_registry`; RESEARCH y GRILL las declaran; SPEC/PLAN/IMPLEMENT no |
| B8 | Filtros de design | `level`/`intent` filtran igual que en K2 |

## 5. Verificación

`tests/adapters/test_graph_tools.py` codifica B1–B8. Auditoría: diff limitado a `adapters/tools/graph_tools.py`, `adapters/tools/registry.py`, `application/phase_registry.py`, `agents/researcher.md`, `agents/griller.md`, tests y worklog.
