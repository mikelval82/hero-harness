# Deterministic check registry

**Checkpoint:** tarea 13

El `spec.md` debe contener una seccion obligatoria:

```markdown
## Deterministic Check Registry (check_registry)

- id: DC1
  requirement: R1 | CA1 | R1,CA1
  type: command | static_inspection | manual
  target: comando, archivo, funcion, flujo o artefacto a revisar
  command: comando exacto si `type: command`; `NOT_APPLICABLE` si no aplica
  expected: resultado observable que debe cumplirse
  evidence_hint: archivo:linea esperado, test esperado, salida esperada o conducta observable
```

Reglas:

- Cada criterio de aceptacion `CA*` debe tener al menos un `DC*`.
- Cada `DC*` debe apuntar a uno o mas ids `R*`/`CA*` mediante `requirement:`.
- `type: command` se reserva para comandos locales baratos y deterministas.
- `type: static_inspection` se usa cuando basta revisar un archivo, funcion, prompt o artefacto.
- `type: manual` se usa para conducta observable que no tiene comando local fiable.

El reviewer debe copiar el resultado en `audit.md`:

```markdown
### Deterministic Check Registry (check_registry)
- registry_source: spec.md#Deterministic Check Registry
- checks_executed: DC1,DC2
- failed_checks: none
- not_run_checks: none
- DC1:
  requirement: CA1
  type: command
  status: PASS
  evidence: `.venv\Scripts\python.exe -m pytest ...` -> passed
```

Politica de aprobacion:

- Un `FAIL` bloquea aprobacion si esta ligado a un criterio de aceptacion.
- Un `NOT_RUN` bloquea aprobacion salvo que el reviewer aporte evidencia alternativa equivalente.
- Los claims de `status.md` no sustituyen estos checks; solo sirven como pistas.
