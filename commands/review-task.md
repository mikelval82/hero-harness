> En modo autonomo (`mission.sh`), este command se bypasea. Las instrucciones
> del agente se pasan directamente via `claude -p`.

Lee `~/.claude/agents/reviewer.md` y sigue su protocolo completo.

Foco adicional del usuario: $ARGUMENTS

## Workspace

Ruta de artefactos: `$CLAUDE_HARNESS/`

- Todos los artefactos se leen de ahi.
- NUNCA escribas artefactos dentro del directorio del proyecto.

## Nota

Si existe un script `mission-validate` en la raiz del proyecto (`.cmd`, `.bat`, `.ps1` o `.sh`), ejecutalo.
NO limpies el workspace despues del review.
