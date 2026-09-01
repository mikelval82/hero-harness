# O1 — Consultas factuales del grafo de código

## Contrato v2

`CodeGraph` y `POST /api/v1/code-graph/query` comparten exactamente las acciones
`find_nodes`, `dependencies`, `dependents`, `impact_analysis` y `dead_code`.
Ambos usan exclusivamente `code_graph.db` de la misión activa y devuelven
`observed_revision`, columnas, filas y recuento.

La consulta es de sólo lectura: abre SQLite en modo `ro`, activa `query_only`,
admite únicamente una lista cerrada de campos y limita cada resultado a 200
filas. No acepta SQL, rutas de base, comandos de build ni shell del cliente o
del modelo. El worker conserva su autenticación loopback existente.

## Precisión de los hechos

Las relaciones se publican sólo cuando el extractor posee un identificador de
nodo observado exacto. Referencias léxicas y nombres de herencia no resueltos
no se convierten en enlaces inferidos. Por ello los archivos fuente siguen
siendo la autoridad cuando se requiere semántica de llamadas o resolución de
imports.

## Evidencia exigida

- Agente y HTTP devuelven la misma forma de respuesta para el mismo grafo.
- El endpoint aparece en OpenAPI y en `capabilities`.
- Campos `sql` o `db`, límites fuera de rango y nodos inexistentes se rechazan.
- La suite incluye una prueba Windows que confirma el cierre de la conexión
  read-only antes de limpiar el workspace temporal.

## Límite deliberado

O1 no construye ni refresca el grafo durante una consulta. La construcción sigue
siendo responsabilidad del ciclo de misión; una respuesta con revisión concreta
no asegura que el código haya cambiado después de esa observación.
