> En modo autonomo (`mission.sh`), este command se bypasea. Las instrucciones
> del agente se pasan directamente via `claude -p`.

Lee `~/.claude/agents/specifier.md` y sigue su protocolo completo.

El usuario quiere especificar una tarea del sprint: $ARGUMENTS

Si no se indica tarea especifica, usa la primera tarea pendiente de `$CLAUDE_HARNESS/tasks.json`.

## Workspace

Ruta de artefactos: `$CLAUDE_HARNESS/`

- El workspace ya esta preparado. NO lo limpies.
- Todos los artefactos se escriben ahi.
- NUNCA escribas artefactos dentro del directorio del proyecto.
