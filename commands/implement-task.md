> En modo autonomo (`mission.sh`), este command se bypasea. Las instrucciones
> del agente se pasan directamente via `claude -p`.

Lee `~/.claude/agents/implementer.md` y sigue su protocolo completo.

Indicaciones adicionales del usuario: $ARGUMENTS

## Workspace

Ruta de artefactos: `$CLAUDE_HARNESS/`

- El workspace ya esta preparado. NO lo limpies.
- Todos los artefactos se escriben ahi.
- NUNCA escribas artefactos dentro del directorio del proyecto.

## Nota

Crea `status.md` desde cero (no esperes uno previo del planner).
Si existe un script `mission-validate` en la raiz del proyecto (`.cmd`, `.bat`, `.ps1` o `.sh`), ejecutalo antes de reportar.
