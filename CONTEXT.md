# Lenguaje Compartido — Metodologia Harness Engineering

Vocabulario preciso de la metodologia. Agentes y humanos usan estos terminos
para comunicarse sin ambiguedad.

## Roles

**Agente**:
Un agente especializado que ejecuta una fase del pipeline (researcher,
specifier, planner, implementer, reviewer). En modo autonomo, cada agente
se invoca directamente via `claude -p` — no hay intermediarios.
_Evitar_: subagente, worker, helper

## Artefactos del pipeline

**Pizarra compartida (layered context)**:
Sistema de dos capas para compartir hallazgos del codebase entre agentes:
- `context-hot.md` — capa activa: hallazgos de la tarea actual, se elimina tras compactar
- `context-cold.md` — capa persistente: conocimiento acumulado de todas las tareas anteriores
Solo hechos verificables, no opiniones. La compactacion (hot → cold append) es automatica.
_Evitar_: log, notas, resumen

**Spec**:
La especificacion tecnica en `spec.md`. Define que se va a construir, con
criterios de aceptacion claros.
_Evitar_: requisitos, brief, descripcion

**Plan**:
Los pasos de implementacion concretos en `plan.md`. Define como se va a construir.
_Evitar_: roadmap, diseno, estrategia

**Audit**:
El veredicto del reviewer en `audit.md`. Aprueba o rechaza el trabajo
comparandolo contra spec, plan y checkpoints.
_Evitar_: review, feedback, evaluacion

## Herramientas

**Skill**:
Un slash command (archivo `.md` en `~/.claude/commands/`) que encapsula un
proceso repetible. Los skills son pequenos, componibles y adaptables.
_Evitar_: comando, macro, receta

**Grill**:
Sesion de interrogatorio exhaustivo donde el agente desafia el plan del
usuario, resuelve ambiguedades y cristaliza decisiones antes de implementar.
_Evitar_: entrevista, brainstorm, reunion

**Feedback loop**:
Un mecanismo de verificacion rapido, determinista y ejecutable que da senal
de pass/fail sobre el estado del codigo o contenido.
_Evitar_: test, chequeo, validacion

**Workspace efimero**:
El directorio runtime apuntado por `$CLAUDE_HARNESS` donde los agentes escriben
sus artefactos. En ejecucion normal se crea como
`$HOME/.harness/<project>/<branch-safe>/`. Es distinto del proyecto target:
el harness guarda artefactos; el target recibe los cambios de codigo.
_Evitar_: carpeta de trabajo, output, dev folder

## Relaciones

- `mission.sh` compone prompts y lanza agentes directamente via `claude -p`
- `tasks.json` define las tareas; cada tarea pasa por spec, plan, implement, review
- Los agentes enriquecen `context-hot.md` (pizarra compartida) con hallazgos de primera mano
- El **Audit** cierra el ciclo validando contra **Checkpoints**

## Ambiguedades resueltas

- "review" se usaba para el veredicto del reviewer y para revision general —
  resuelto: el veredicto es el **Audit**, la accion del skill es `/review-task`.
- "plan" se usaba tanto para plan de implementacion como para planificacion
  general — resuelto: **Plan** refiere exclusivamente a `plan.md` del pipeline.
- "sprint.md" era redundante con `tasks.json` — eliminado. Las tareas se
  definen exclusivamente en `tasks.json`.
