# Skill library post-mision

## Objetivo

La skill library guarda procedimientos verificados por proyecto para que futuras
misiones puedan reutilizar "como hacer" sin depender solo de memoria narrativa o
casos episodicos.

La separacion es deliberada:

- `PROJECT_MEMORY.md`: convenciones, comandos, restricciones y fallos recurrentes.
- `cases.jsonl`: episodios aprobados, utiles como ejemplos concretos.
- `skills.jsonl` + `skills/*.md`: procedimientos reutilizables con triggers y
  verificacion esperada.

## Ubicacion persistente

Cada proyecto tiene su directorio en:

```text
$HOME/.harness-memory/<project-key>/
```

Dentro de ese directorio:

```text
skills.jsonl
skills/
  prompt-gate-contract-change.md
```

Durante una mision, el harness prepara:

```text
$CLAUDE_HARNESS/retrieved-skills.md
$CLAUDE_HARNESS/_project_skills_path
$CLAUDE_HARNESS/generated-skills/
```

`retrieved-skills.md` es contexto read-only para fases agenticas. `_project_skills_path`
apunta al directorio persistente `skills/`. `generated-skills/` es la bandeja donde
el reporte final puede dejar una skill nueva si la mision produjo un procedimiento
verificado.

## Formato de skill

Cada skill es un Markdown con frontmatter simple:

```markdown
---
skill_id: short-kebab-case-id
name: Human Readable Name
version: 1
status: verified
source: mission-report
evidence: task/status/audit/test evidence
triggers:
  - trigger phrase
---
# Human Readable Name

## When To Use
...

## Procedure
1. ...

## Required Verification
- ...

## Evidence
- ...

## Risks
- ...
```

Reglas:

- Solo se promocionan skills con `status: verified`.
- La evidencia debe apuntar a artefactos reales: `status.md`, `audit.md`, tests,
  reporte de mision o checkpoints.
- Una skill describe un procedimiento, no un resultado historico.
- Si el trigger no encaja, el agente debe ignorarla.
- El agente siempre debe verificar contra el codebase actual.

## Recuperacion

`stage_retrieved_skills(...)` inicializa la library, recupera top-k skills por
solapamiento lexical con la tarea y escribe `retrieved-skills.md`.

Las fases que reciben `RETRIEVED_SKILLS` son:

- research
- structure
- grill
- spec
- plan
- implement
- implement_bursts
- review
- reimplement

Los prompts instruyen a usar estas skills como procedimientos verificados, no como
autoridad sobre el estado actual del repositorio.

## Promocion post-mision

El reporte final puede escribir exactamente una skill nueva bajo:

```text
$CLAUDE_HARNESS/generated-skills/<skill-id>.md
```

`MissionRunner._generate_report()` ejecuta `sync_generated_skills(...)` despues del
reporte. La sincronizacion:

1. Lee `_project_skills_path`.
2. Revisa cada Markdown en `generated-skills/`.
3. Promociona solo archivos con `status: verified`.
4. Copia el archivo a `skills/<skill-id>.md`.
5. Actualiza `skills.jsonl` con metadata y texto de recuperacion.

## Primer ejemplo

La library se inicializa con `prompt-gate-contract-change`, una skill semilla para
cambios que afectan contratos entre prompts, agentes, gates, includes y tests.

Trigger principal:

- prompt contract
- gate marker
- phase include
- agent signature
- deterministic check

Valor:

- Evita olvidar una de las superficies de contrato.
- Fuerza tests de wiring (`test_context.py`), contratos (`test_prompt_contracts.py`)
  y setup/runner cuando hay staging o sincronizacion.
- Captura el patron repetido en las tareas 8, 13, 14 y 15.

## Riesgos pendientes

- La similitud es lexical simple; con mas datos podria evolucionar a BM25 o vectorial.
- La promocion depende de que el reporte cree skills de calidad; el runner solo
  filtra `status: verified`, no audita semanticamente la utilidad.
- No hay deduplicacion semantica avanzada; por ahora se evita duplicar por
  `skill_id`.
