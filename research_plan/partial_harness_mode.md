# Partial harness mode

## Objetivo

Disponer de rutas de bajo coste para medir cuanto valor aporta el harness antes de implementar:

- `spec`: produce investigacion, grill opcional, estructura de tareas y `spec.md` por tarea.
- `spec-plan`: produce lo anterior y ademas `plan.md` + `decisions.md`.

Estos modos no ejecutan implementacion, review ni merge. Sirven para benchmarkear el coste y la calidad de artefactos intermedios frente al modo `full`.

## CLI

```text
.\bin\mission.bat --mode spec "Add deterministic check registry for X"
.\bin\mission.bat --mode spec-plan "Add deterministic check registry for X"
.\bin\mission.bat --spec-only "Add deterministic check registry for X"
.\bin\mission.bat --spec-plan "Add deterministic check registry for X"
```

## Pipeline

| Modo | Init | Tarea | Finalize |
|------|------|-------|----------|
| `spec` | `research -> grill? -> structure` | `spec` | `report` |
| `spec-plan` | `research -> grill? -> structure` | `spec -> plan` | `report` |

## Artefactos esperados

- `brainstorm.md`, `brief.md` si hubo grill, `tasks.json`.
- `spec.md` en `spec` y `spec-plan`.
- `plan.md` y `decisions.md` solo en `spec-plan`.
- `mission-report.md` con resumen de analisis, coste y recomendaciones.
- `_telemetry.jsonl` con eventos de tarea y coste/token por fase.

## Tarea de prueba para benchmark

Usar la misma descripcion en los tres modos y comparar:

```text
Add a deterministic check registry entry to the spec workflow and make the reviewer consume it.
```

Ejecuciones sugeridas:

```text
.\bin\mission.bat --mode spec --max-tasks 1 "Add a deterministic check registry entry to the spec workflow and make the reviewer consume it."
.\bin\mission.bat --mode spec-plan --max-tasks 1 "Add a deterministic check registry entry to the spec workflow and make the reviewer consume it."
.\bin\mission.bat --mode full --max-tasks 1 "Add a deterministic check registry entry to the spec workflow and make the reviewer consume it."
```

Metricas:

- tokens y coste desde el `TOKEN/COST SUMMARY` del reporte.
- numero de fases ejecutadas desde `_telemetry.jsonl`.
- calidad manual de `spec.md` y `plan.md`.
- tasa de utilidad: si el modo parcial produjo suficiente informacion para implementar con menos retry.

## Cierre de seguridad

Los modos parciales marcan la tarea como completada solo dentro del harness, compactan contexto y generan reporte. No llaman a `stage_task_files`, `commit_task`, `final_commit` ni `merge_to_develop`.
