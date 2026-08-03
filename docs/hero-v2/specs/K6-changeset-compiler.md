# K6 — Compilador ChangeSet

Spec completa. Función pura y determinista que convierte un Approved Snapshot (K5) más el conjunto de declaraciones observadas (K1) en el conjunto estructurado de operaciones de cambio. Deriva de las secciones 3 y 8 de [hero-v2-grafo-vivo.md](../../hero-v2-grafo-vivo.md).

## 1. Alcance

Entra: `compile_changeset(snapshot, observed_ids) -> ChangeSet` como lógica de dominio pura (sin IO, sin SQLite, sin LLM), con operaciones deterministas, precondiciones, omisiones justificadas y diagnósticos.

No entra: agrupación en WorkPlan, validador de cobertura y structurer (K7); persistencia del changeset (K7 lo serializa como artefacto); reconciliación (K9).

## 2. Decisiones de contrato

**Pureza total.** La entrada es el snapshot (dict tal como lo exporta K5) y el conjunto de ids observados (`set[str]` de la capa de hechos). Nada de conexiones: quien llama resuelve la observación. Mismo input → mismo output, byte a byte tras serializar.

**La intención manda; la resolución valida.** Cada nodo del snapshot produce según su `intent`:

| intent | locator resuelto | resultado |
| --- | --- | --- |
| KEEP | — | sin operación (contexto) |
| CREATE | no (o sin locator) | operación `CREATE_NODE` |
| CREATE | sí | **omitida** con motivo `already_materialized` |
| CHANGE | sí | operación `MODIFY_NODE` |
| CHANGE | no / sin locator | **issue** bloqueante (no se puede cambiar lo no observado) |
| REMOVE | sí | operación `REMOVE_NODE` |
| REMOVE | no / sin locator | **issue** bloqueante |

Los nodos `EXTERNAL` con intent `CREATE` sí emiten operación (aprovisionar infraestructura es trabajo real), sin precondición de locator.

**Aristas.** `intent=CREATE` → `CONNECT` con `depends_on` hacia las operaciones `CREATE_NODE` de sus extremos si existen; `intent=REMOVE` → `DISCONNECT`; `KEEP` → nada. Las aristas arquitectónicas **no** generan dependencias de ejecución entre nodos (sección 8 de la visión): solo las dependencias estructurales evidentes (no se puede conectar lo que aún no existe).

**Identidades deterministas.** `create:<node_id>`, `change:<node_id>`, `remove:<node_id>`, `connect:<source>-><target>:<relation>`, `disconnect:<source>-><target>:<relation>`. Salida ordenada por id de operación, independiente del orden de entrada.

**Los issues no abortan la compilación.** El ChangeSet completo (operaciones + omitidas + issues) es el informe; decidir si un issue bloquea el plan es responsabilidad del validador de K7 y del humano.

## 3. Contrato

```python
@dataclass(frozen=True)
class ChangeOperation:
    id: str; kind: str; target_node: str
    locator: str | None; level: str; location: str
    depends_on: tuple[str, ...]; description: str

@dataclass(frozen=True)
class ChangeSet:
    snapshot_id: str
    operations: tuple[ChangeOperation, ...]
    skipped: tuple[SkippedChange, ...]
    issues: tuple[ChangeIssue, ...]

def compile_changeset(snapshot: dict, observed_ids: set[str]) -> ChangeSet
```

## 4. Tabla de aceptación

| # | Caso | Resultado esperado |
|---|------|--------------------|
| C1 | Nodo CREATE sin resolver + nodo KEEP | una op `create:<id>`; KEEP no produce nada |
| C2 | Nodo CREATE cuyo locator ya resuelve | sin operación; entrada en `skipped` con `already_materialized` |
| C3 | CHANGE resuelto / CHANGE sin locator / CHANGE sin resolver | `change:<id>` / issue / issue; los issues no producen operación |
| C4 | REMOVE resuelto / REMOVE sin resolver | `remove:<id>` / issue |
| C5 | Arista CREATE entre dos nodos CREATE; arista KEEP; arista REMOVE | `connect` con depends_on a ambos `create:`; nada; `disconnect` |
| C6 | Mismo snapshot con nodos en orden distinto | ChangeSets idénticos tras serializar (determinismo) |
| C7 | ChangeSet | conserva `snapshot_id` del snapshot de entrada |
| C8 | Nodo EXTERNAL con intent CREATE | operación emitida con `location=EXTERNAL`, sin issue |

## 5. Verificación

`tests/domain/test_changeset.py` codifica C1–C8. Auditoría: diff limitado a `domain/changeset.py`, spec, tests y worklog; sin IO ni dependencias nuevas.
