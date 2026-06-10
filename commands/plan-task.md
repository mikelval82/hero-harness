> En modo autonomo (`mission.sh`), este command se bypasea. Las instrucciones
> del agente se pasan directamente via `claude -p`.

Lee `~/.claude/agents/planner.md` y sigue su protocolo completo.

Contexto adicional del usuario: $ARGUMENTS

## Workspace

Ruta de artefactos: `$CLAUDE_HARNESS/`

- El workspace ya esta preparado. NO lo limpies.
- Todos los artefactos se escriben ahi.
- NUNCA escribas artefactos dentro del directorio del proyecto.

## Nota

No generes `status.md`. Solo produce: `plan.md` y `decisions.md`.
