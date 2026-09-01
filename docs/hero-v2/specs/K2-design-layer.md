# K2 — Capa de diseño: esquema, operaciones y revisión

Spec completa. Contrato del almacén de diseño que consumirán K4 (herramientas de agente), K5 (aprobación CAS) y K6 (compilador). Deriva de las secciones 4, 6 y 7 de [hero-v2-grafo-vivo.md](../../hero-v2-grafo-vivo.md).

## 1. Alcance

Entra: tablas de diseño en SQLite propio, dimensiones separadas, localizadores esperados, log de operaciones idempotente con CAS sobre revisión global, resolución calculada contra la capa de hechos, versión de esquema no destructiva.

No entra (diferido por debate): bloqueo por entidad, undo compensatorio, snapshots aprobados (K5), ámbitos de persistencia proyecto/misión (K3), herramientas de agente (K4).

## 2. Decisiones de contrato

**Base de datos separada de los hechos.** `design.db`, no tablas dentro de `code_graph.db`. Motivo: la política de migración de los hechos es destructiva (D-1.3, drop y reconstruir); la capa de diseño es autoral y jamás puede heredar esa política. Separar ficheros hace estructuralmente imposible el accidente.

**Migración de diseño: fallar, nunca dropear.** `PRAGMA user_version`; si el fichero tiene versión distinta a la soportada, se lanza error con mensaje accionable. No hay reconstrucción automática de datos autorales.

**Dimensiones como columnas de texto validadas por enum de dominio.** `provenance` (ANALYZER/HUMAN/AGENT), `location` (IN_REPOSITORY/EXTERNAL), `intent` (KEEP/CREATE/CHANGE/REMOVE), `level` (SYSTEM/PACKAGE/CODE). La resolución **no se almacena**: se calcula resolviendo `locator` contra la capa de hechos en el momento de la consulta.

**Identidad lógica separada del localizador.** `id` es una identidad estable del nodo de diseño (la asigna el llamante); `locator` es el ancla esperada hacia los hechos (formato = id de nodo de hechos, p. ej. `src/cache/redis.py:RedisCache`), nullable.

**Revisión global + operación idempotente.** Cada `apply()` declara `base_revision` (CAS contra la revisión global, D del debate: sin bloqueo por entidad) y un `operation_id` único. Un lote es atómico: o se aplica entero o se rechaza entero. Todo intento —aplicado, conflicto o rechazo— queda en el log `operations` con autor, timestamp y resultado.

**Provenance inmutable.** `update_node` no puede cambiar quién introdujo el elemento.

## 3. Contrato de API

```python
class DesignStore:
    def current_revision(self) -> int
    def apply(self, *, operation_id: str, author: str, base_revision: int,
              operations: list[dict]) -> ApplyResult
    def nodes(self, *, level=None, parent_id=None, intent=None) -> list[DesignNode]
    def edges(self) -> list[DesignEdge]
    def history(self) -> list[OperationRecord]
    def resolution_for(self, node: DesignNode, facts: SQLiteCodeGraph) -> Resolution
```

Operaciones del lote: `add_node`, `update_node`, `remove_node`, `add_edge`, `remove_edge`.

`ApplyResult.status`: `APPLIED` | `CONFLICT` (base_revision obsoleta) | `REJECTED` (validación) | `DUPLICATE` (operation_id ya visto; devuelve el resultado original sin reaplicar).

Validaciones que rechazan el lote completo: tipo de operación desconocido, nodo duplicado en `add_node`, `update/remove` sobre nodo inexistente, arista con extremo inexistente (considerando los efectos previos del propio lote), `parent_id` inexistente, valor de dimensión fuera de enum, intento de cambiar `provenance`.

## 4. Tabla de aceptación

| # | Caso | Entrada | Resultado esperado |
|---|------|---------|--------------------|
| A1 | Alta básica | `apply` con `add_node` + `add_edge` válidos sobre revisión actual | `APPLIED`, revisión +1, nodo y arista consultables con sus dimensiones |
| A2 | CAS | `apply` con `base_revision` obsoleta | `CONFLICT`, nada aplicado, revisión intacta |
| A3 | Idempotencia | Reenvío del mismo `operation_id` | `DUPLICATE` con la revisión del intento original, sin reaplicar, revisión intacta |
| A4 | Atomicidad | Lote con op válida + arista hacia nodo inexistente | `REJECTED`, ninguna op del lote aplicada, revisión intacta |
| A5 | Validación | `update_node` sobre id inexistente; op de tipo desconocido; `provenance` en update | `REJECTED` en los tres casos |
| A6 | Resolución calculada | Nodo IN_REPOSITORY con locator presente en hechos → RESOLVED; locator ausente → UNRESOLVED; nodo EXTERNAL → EXTERNAL | según cada caso, sin columna almacenada |
| A7 | Auditoría | Tras A1–A4, `history()` | registros con operation_id, autor, base_revision y status de cada intento, en orden |
| A8 | Migración segura | Abrir un `design.db` con `user_version` distinto | excepción explícita; los datos no se tocan |
| A9 | Filtros | `nodes(level=…)`, `nodes(parent_id=…)`, `nodes(intent=…)` | subconjuntos correctos |

## 5. Verificación

`tests/adapters/test_design_store.py` codifica A1–A9. Auditoría de cierre: el diff no toca nada fuera de `domain/design.py`, `adapters/design/`, tests y worklog; los tests de aceptación no se modifican para pasar.
