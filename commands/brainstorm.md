> En modo autonomo (`mission.sh`), este command se bypasea. Las instrucciones
> del agente se pasan directamente via `claude -p`.

Lee `~/.claude/agents/researcher.md` y sigue su protocolo completo.

El usuario quiere explorar un problema o idea: $ARGUMENTS

## Workspace

Ruta de artefactos: `$CLAUDE_HARNESS/`

- Si el workspace no existe, crealo con `mkdir -p $CLAUDE_HARNESS/`.
- Todos los artefactos se escriben ahi.
- NUNCA escribas artefactos dentro del directorio del proyecto.

## Nota

No generes `sprint.md`. Genera solo: `brainstorm.md`, `tasks.json`, `context-hot.md`.
