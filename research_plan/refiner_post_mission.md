# Refiner post-mision con aprobacion humana

## Objetivo

El refiner post-mision convierte fallos recurrentes en propuestas de mejora del
harness. No cambia prompts ni agentes por si mismo: solo escribe una propuesta
revisable por una persona.

La regla central es:

```text
fallos recurrentes -> propuesta -> aprobacion humana -> tarea normal
```

Nunca:

```text
fallos recurrentes -> auto-edicion de prompts/agentes
```

## Artefactos

El proceso offline escribe:

```text
$CLAUDE_HARNESS/refiner-proposal.md
```

Lee, si existen:

- `audit.md`
- `status.md`
- `mission-report.md`
- `_telemetry.jsonl`
- `retrieved-cases.md`
- `retrieved-skills.md`
- `project-memory.md`
- `cases.jsonl` via `_project_cases_path`

## Prompt

El prompt operativo vive en:

```text
prompts/refiner-prompt.md
```

Contrato principal:

- phase: `refiner_offline`
- outputs: `refiner-proposal.md` solamente
- `approval_required: true`
- `auto_apply: false`
- prohibido editar prompts, agentes, codigo, tests, memoria, casos o skills

## Comando

El comando manual es:

```text
/refine-harness
```

Y el subcomando determinista de soporte:

```text
python src/harness/harness_utils.py refiner-proposal "$CLAUDE_HARNESS"
```

Opcionalmente acepta:

```text
python src/harness/harness_utils.py refiner-proposal <harness_path> <min_recurrence>
```

## Proceso

1. Recoger senales de fallo desde taxonomy, retries, rechazos, tareas fallidas y
   case base.
2. Agrupar por firma `failure_type@recoverability_lost_at_stage`.
3. Considerar recurrente una firma solo si aparece al menos dos veces.
4. Proponer como maximo una mejora por firma recurrente.
5. Escribir propuesta con target artifacts, evidencia, valor esperado, riesgo y
   checklist de aprobacion humana.
6. No aplicar nada.

## Ejemplo de propuesta no aplicada automaticamente

```markdown
---
status: proposed
approval_required: true
auto_apply: false
generated_by: offline_refiner
min_recurrence: 2
---
# Refiner Proposal

This proposal is advisory. It must not be applied automatically.
A human must review the evidence, edit the proposed change, and apply it manually.

## Evidence Reviewed
- failure_signals: 2
- recurrent_signatures: 1
- proposal_file_only: refiner-proposal.md

## Recurrent Failure Signatures
- missing_test@spec: 2 signals
  - audit.md: failure_type: missing_test recoverability_lost_at_stage: spec
  - cases.jsonl: failure_type: missing_test recoverability_lost_at_stage: spec

## Proposed Harness Changes
### RP1: Strengthen deterministic check coverage
- failure_signature: missing_test@spec
- observed_count: 2
- change_type: prompt_contract
- target_artifacts:
  - prompts/spec-prompt.md
  - prompts/review-prompt.md
- proposed_change: require a cheap deterministic check for the recurring missed behavior.
- expected_value: reduce recurrence of this exact failure signature.
- risk: prompt overfitting if the signature is incidental or too sparse.
- approval_required: true
- auto_apply: false

## Human Approval
- Review whether the signature is causal, repeated, and worth changing the harness for.
- If approved, create a normal implementation task and update prompts/agents with tests.
- If rejected, leave this proposal as historical evidence and make no harness changes.

## Non-Application Guarantee
- This process only writes `refiner-proposal.md`.
- It does not edit prompts, agents, code, tests, memory, cases, or skills.
```

## Riesgos pendientes

- La deteccion de recurrencia es lexical/estructural, no semantica.
- Una firma repetida puede ser incidental; por eso la aprobacion humana es
  obligatoria.
- El refiner no debe ejecutarse mid-mission: solo post-mision u offline.
