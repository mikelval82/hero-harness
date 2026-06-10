# Checkpoints — mejoras del harness

**Fecha de creación:** 2026-05-27

Este archivo registra el avance de implementación de las mejoras priorizadas del harness. La regla es simple: una tarea solo se marca como completada cuando tiene **cambio aplicado**, **verificación mínima** y **evidencia registrada**.

Estados:

| Estado | Significado |
|--------|-------------|
| `[ ]` | Pendiente |
| `[~]` | En curso |
| `[x]` | Completada |
| `[!]` | Bloqueada o necesita decisión |

---

## 1. Backlog priorizado

| Estado | # | Tarea | Criterio de cierre | Evidencia esperada |
|--------|---|-------|--------------------|--------------------|
| `[x]` | 1 | Diagnosis/reflection gate tras fallo | El reimplement loop exige diagnóstico estructurado antes de editar tras fallo. | Prompt/gate actualizado + ejemplo de `audit` o `status` con diagnosis. |
| `[x]` | 2 | Separar `technical_review` y `semantic_audit` | El reviewer emite ambas secciones de forma estable. | `reviewer.md` actualizado + ejemplo de salida. |
| `[x]` | 3 | `audit.md` como gradiente textual por variable/artefacto | Cada finding apunta a variable, role, objective, feedback y required_change. | Formato documentado + ejemplo real. |
| `[x]` | 4 | Failure taxonomy mínima | Rechazos/intervenciones registran `failure_type` y etapa donde se perdió recuperabilidad. | Taxonomía añadida a prompt/formato + caso de prueba manual. |
| `[x]` | 5 | Spec re-injection en bursts y retries | Cada burst/retry recibe objetivo, criterios, constraints, non-goals y fallos actuales. | Prompt o runner actualizado + muestra de contexto inyectado. |
| `[x]` | 6 | Self-verification local antes del reviewer | Implementer declara checks ejecutados, criterios cubiertos, riesgos y archivos revisados. | `status.md` o prompt actualizado + ejemplo. |
| `[x]` | 7 | Check de evaluation hacking | Reviewer comprueba hardcoding, special-casing y satisfacción superficial de acceptance criteria. | Sección añadida al reviewer + ejemplo negativo. |
| `[x]` | 8 | Signatures, roles y `requires_grad` conceptual | Prompts/agentes declaran inputs, outputs, responsabilidades y artefactos editables. | Headers actualizados en prompts/agentes principales. |
| `[x]` | 9 | Auditoría evidence-anchored vs instruction-compliance | Reglas de agentes clasificadas y ajustadas si inducen cumplimiento superficial. | Tabla de auditoría o diff en agentes. |
| `[x]` | 10 | Complexity routing S/M/L formalizado | Queda registrada la razón para escoger ruta simple/media/completa. | Campo en brief/status/log + ejemplo. |
| `[x]` | 11 | Telemetry mínima + intervention logger | Misiones registran coste, retries, fallos, HITL y missing component. | Esquema de log + primera traza. |
| `[x]` | 12 | Token/cost budget como restricción primaria | Benchmark o runner reporta tokens/coste por misión. | Métrica visible en output/log. |
| `[x]` | 13 | Deterministic check registry ligado al `spec.md` | El spec lista checks verificables y reviewer los consulta. | Formato de checks + ejecución manual. |
| `[x]` | 14 | Project memory ligera por target-project | Existe mecanismo documentado para recordar convenciones/fallos por repo. | Archivo o directorio de memoria + política de uso. |
| `[x]` | 15 | Mission case base persistente | Misiones aprobadas se guardan y pueden recuperarse por similitud. | Esquema + recuperación simple. |
| `[x]` | 16 | Skill library post-misión | Patrones verificados se guardan como skills reutilizables. | Formato de skill + primer ejemplo. |
| `[x]` | 17 | Refiner post-misión con aprobación humana | Un proceso offline propone mejoras a prompts/agentes desde fallos recurrentes. | Prompt/proceso + ejemplo de propuesta no aplicada automáticamente. |
| `[x]` | 18 | Partial harness mode | Existe ruta spec-only o spec+plan y queda disponible para benchmark. | Configuración de pipeline + tarea de prueba. |

---

## 2. Registro de checkpoints completados

Cada vez que se complete una tarea, añadir una entrada aquí.

### 2026-05-27 — Tarea #1: Diagnosis/reflection gate tras fallo

- Cambio aplicado: `reimplement-prompt.md` exige escribir una seccion `## Diagnosis` en `status.md` antes de modificar codigo durante REIMPLEMENT.
- Archivos modificados:
  - `prompts/reimplement-prompt.md`
  - `src/core/gate.py`
  - `src/tests/test_gate.py`
  - `research_plan/checkpoints.md`
- Verificacion:
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-local src/tests/test_gate.py` -> 18 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-local src/tests/test_mission.py -k check_gate` -> 14 passed.
- Evidencia: `check_gate(..., "reimplement[1.1]")` falla sin `## Diagnosis` y pasa cuando `status.md` incluye la seccion.
- Riesgos pendientes: el orden "antes de editar" queda instruido por prompt; el gate valida el artefacto final, no el orden historico de tool calls.

### 2026-05-27 — Tarea #2: Separar `technical_review` y `semantic_audit`

- Cambio aplicado: `reviewer.md` y `review-prompt.md` exigen que `audit.md` separe `## Technical Review (technical_review)` y `## Semantic Audit (semantic_audit)`.
- Archivos modificados:
  - `agents/reviewer.md`
  - `prompts/review-prompt.md`
  - `src/core/gate.py`
  - `src/tests/test_gate.py`
  - `research_plan/checkpoints.md`
- Verificacion:
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-local src/tests/test_gate.py` -> 20 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-tasks src/tests/test_tasks.py -k AuditVerdict` -> 4 passed.
- Evidencia: `check_gate(..., "review[1.1]")` falla si `audit.md` solo tiene `## Verdict`, y pasa cuando contiene `## Technical Review` y `## Semantic Audit`.
- Riesgos pendientes: el reviewer puede seguir mezclando hallazgos semanticamente si el modelo no obedece; el gate solo garantiza presencia de secciones, no calidad interna.

### 2026-05-27 — Tarea #3: `audit.md` como gradiente textual por variable/artefacto

- Cambio aplicado: `reviewer.md` y `review-prompt.md` exigen `### Gradient Findings (textual_gradients)` dentro de `## Technical Review`, con findings localizados por `variable`, `role`, `objective`, `feedback`, `required_change`, `constraints` y `evidence`.
- Archivos modificados:
  - `agents/reviewer.md`
  - `prompts/review-prompt.md`
  - `src/core/gate.py`
  - `src/tests/test_gate.py`
  - `research_plan/checkpoints.md`
- Verificacion:
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-gate3 src/tests/test_gate.py` -> 21 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-mission3 src/tests/test_mission.py -k check_gate` -> 14 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-tasks3 src/tests/test_tasks.py -k AuditVerdict` -> 4 passed.
- Evidencia: `check_gate(..., "review[1.1]")` falla si falta `### Gradient Findings` y pasa cuando la seccion existe junto a `## Technical Review` y `## Semantic Audit`.
- Riesgos pendientes: el gate valida presencia de la seccion; la completitud de cada campo (`variable`, `role`, `objective`, `feedback`, `required_change`, `constraints`, `evidence`) queda instruida por prompt, no parseada estructuralmente.

### 2026-05-27 — Tarea #4: Failure taxonomy mínima

- Cambio aplicado: `reviewer.md` y `review-prompt.md` exigen `## Failure Taxonomy (failure_taxonomy)` con `failure_type` y `recoverability_lost_at_stage`; para `APPROVED`, ambos deben ser `none`.
- Archivos modificados:
  - `agents/reviewer.md`
  - `prompts/review-prompt.md`
  - `src/core/gate.py`
  - `src/tests/test_gate.py`
  - `research_plan/checkpoints.md`
- Verificacion:
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-gate4b src/tests/test_gate.py` -> 23 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-mission4b src/tests/test_mission.py -k check_gate` -> 14 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-tasks4b src/tests/test_tasks.py -k AuditVerdict` -> 4 passed.
- Evidencia: `check_gate(..., "review[1.1]")` falla si falta `## Failure Taxonomy`, `failure_type:` o `recoverability_lost_at_stage:`, y pasa cuando los campos existen.
- Riesgos pendientes: la taxonomia queda registrada en `audit.md`; las intervenciones HITL humanas aun no tienen logger estructurado propio. Eso corresponde mejor a la tarea 11 (`Telemetry minima + intervention logger`).

### 2026-05-27 — Tarea #5: Spec re-injection en bursts y retries

- Cambio aplicado: `implement-burst-prompt.md` y `reimplement-prompt.md` incluyen un bloque `## Spec re-grounding` que obliga a revisar objetivo, criterios de aceptacion, constraints, non-goals y fallos/riesgos actuales antes de editar.
- Archivos modificados:
  - `prompts/implement-burst-prompt.md`
  - `prompts/reimplement-prompt.md`
  - `src/tests/test_harness_utils.py`
  - `src/tests/test_context.py`
  - `src/tests/test_mission_runner.py`
  - `research_plan/checkpoints.md`
- Verificacion:
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-hu5 src/tests/test_harness_utils.py -k "regrounding or render_prompt"` -> 10 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-context5 src/tests/test_context.py` -> 32 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-runner5 src/tests/test_mission_runner.py -k "run_reimplement or run_implement_bursts"` -> 5 passed.
- Evidencia: los tests comprueban que ambos prompts contienen `## Spec re-grounding` con `Objective`, `Acceptance criteria`, `Constraints`, `Non-goals` y `Current failed checks`; tambien verifican que `IMPLEMENT_BURSTS` recibe `SPEC`/`DECISIONS`/`CONTEXT_HOT`, `REIMPLEMENT` recibe `SPEC`/`AUDIT`/`STATUS`/`CONTEXT_HOT`, y cada burst recibe `PLAN_STEP`, `PROGRESS` y `FINAL_INSTRUCTIONS`.
- Riesgos pendientes: no se parsean secciones concretas del spec en variables separadas; el agente recibe el spec completo y el prompt le obliga a extraer las partes relevantes. Un extractor estructurado de spec podria ser una mejora futura si el formato EARS se estabiliza.

### 2026-05-27 — Tarea #6: Self-verification local antes del reviewer

- Cambio aplicado: `implementer.md`, `implement-prompt.md`, `reimplement-prompt.md` y las instrucciones finales de bursts exigen `## Self-Verification` en `status.md` con `tests_run`, `acceptance_criteria_checked`, `edge_cases_considered`, `files_touched_reviewed`, `harness_artifacts_not_written_to_target` y `known_risks`.
- Archivos modificados:
  - `agents/implementer.md`
  - `prompts/implement-prompt.md`
  - `prompts/reimplement-prompt.md`
  - `src/mission/burst_runner.py`
  - `src/core/gate.py`
  - `src/tests/test_gate.py`
  - `src/tests/test_harness_utils.py`
  - `src/tests/test_mission_runner.py`
  - `research_plan/checkpoints.md`
- Verificacion:
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-gate6 src/tests/test_gate.py` -> 26 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-hu6 src/tests/test_harness_utils.py -k "self_verification or regrounding or render_prompt"` -> 11 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-runner6 src/tests/test_mission_runner.py -k "run_reimplement or run_implement_bursts"` -> 5 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-mission6 src/tests/test_mission.py -k check_gate` -> 14 passed.
- Evidencia: `check_gate(..., "implement[1.1]")` falla sin `## Self-Verification` y pasa cuando existe; `check_gate(..., "reimplement[1.1]")` exige `## Diagnosis` y `## Self-Verification`. El ultimo burst incluye `## Self-Verification` en `FINAL_INSTRUCTIONS`.
- Riesgos pendientes: el gate valida presencia de la seccion, no la calidad factual de cada campo. El reviewer debe auditar si la self-verification es real o superficial.

### 2026-05-27 — Tarea #7: Check de evaluation hacking

- Cambio aplicado: `reviewer.md` y `review-prompt.md` exigen `### Evaluation Hacking Check (evaluation_hacking_check)` dentro de `## Technical Review`, con revision explicita de hardcoding, special-casing de tests y satisfaccion superficial de acceptance criteria.
- Archivos modificados:
  - `agents/reviewer.md`
  - `prompts/review-prompt.md`
  - `src/core/gate.py`
  - `src/tests/test_gate.py`
  - `research_plan/checkpoints.md`
- Verificacion:
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-gate7 src/tests/test_gate.py` -> 28 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-mission7 src/tests/test_mission.py -k check_gate` -> 14 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-tasks7 src/tests/test_tasks.py -k AuditVerdict` -> 4 passed.
- Evidencia: `check_gate(..., "review[1.1]")` falla si falta `### Evaluation Hacking Check`, `hardcoding_outputs:`, `special_casing_tests:` o `superficial_acceptance:`, y pasa cuando esos campos existen.
- Riesgos pendientes: el gate valida que el reviewer declare el check; detectar hacks sutiles depende de evidencia real, tests ocultos y calidad del reviewer.

### 2026-05-27 â€” Tarea #8: Signatures, roles y `requires_grad` conceptual

- Cambio aplicado: agentes y prompts de fase declaran una firma explicita con inputs, outputs, responsabilidades y `editable_artifacts (requires_grad)`. Los agentes tambien declaran `read_only_artifacts (no_grad)` para separar superficie editable de contexto solo lectura.
- Archivos modificados:
  - `agents/researcher.md`
  - `agents/griller.md`
  - `agents/structurer.md`
  - `agents/specifier.md`
  - `agents/planner.md`
  - `agents/implementer.md`
  - `agents/reviewer.md`
  - `agents/content_reviewer.md`
  - `prompts/brainstorm-prompt.md`
  - `prompts/grill-prompt.md`
  - `prompts/structure-prompt.md`
  - `prompts/spec-prompt.md`
  - `prompts/plan-prompt.md`
  - `prompts/implement-prompt.md`
  - `prompts/implement-burst-prompt.md`
  - `prompts/review-prompt.md`
  - `prompts/reimplement-prompt.md`
  - `prompts/compact-prompt.md`
  - `prompts/consolidate-prompt.md`
  - `prompts/report-full-prompt.md`
  - `prompts/report-plan-only-prompt.md`
  - `src/tests/test_prompt_contracts.py`
  - `research_plan/checkpoints.md`
- Verificacion:
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-contract8 src/tests/test_prompt_contracts.py` -> 2 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-hutils8 src/tests/test_harness_utils.py -k "render_prompt or signature or regrounding or self_verification"` -> 11 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-context8 src/tests/test_context.py` -> 32 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-gate8 src/tests/test_gate.py` -> 28 passed.
- Evidencia: `test_prompt_contracts.py` recorre todos los agentes y templates registrados en `PHASE_REGISTRY` y falla si falta `## Signature`/`## Prompt Signature`, `inputs`, `outputs`, `responsibilities` o `editable_artifacts (requires_grad)`.
- Riesgos pendientes: el contrato es declarativo; todavia no impide por si solo que un agente edite fuera de su superficie. Esa restriccion queda reforzada por prompts, reviewer y futuras tareas de auditoria/telemetry.

### 2026-05-27 — Tarea #9: Auditoria evidence-anchored vs instruction-compliance

- Cambio aplicado: se clasificaron reglas con riesgo de cumplimiento superficial en `research_plan/evidence_anchored_instruction_audit.md` y se ajustaron agentes/prompts para tratar `status.md`, checkboxes y self-verification como claims que requieren evidencia.
- Archivos modificados:
  - `agents/specifier.md`
  - `agents/planner.md`
  - `agents/implementer.md`
  - `agents/reviewer.md`
  - `prompts/spec-prompt.md`
  - `prompts/plan-prompt.md`
  - `prompts/implement-prompt.md`
  - `prompts/implement-burst-prompt.md`
  - `prompts/reimplement-prompt.md`
  - `prompts/review-prompt.md`
  - `src/core/gate.py`
  - `src/tests/test_gate.py`
  - `src/tests/test_prompt_contracts.py`
  - `research_plan/evidence_anchored_instruction_audit.md`
  - `research_plan/checkpoints.md`
- Verificacion:
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-gate9 src/tests/test_gate.py` -> 30 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-contract9 src/tests/test_prompt_contracts.py` -> 3 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-mission9 src/tests/test_mission.py -k check_gate` -> 14 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-hutils9 src/tests/test_harness_utils.py -k "render_prompt or self_verification or regrounding or signature"` -> 11 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-tasks9 src/tests/test_tasks.py -k AuditVerdict` -> 4 passed.
- Evidencia: `check_gate(..., "review[1.1]")` ahora falla si falta `### Evidence Anchoring`, `status_claims_checked:`, `unsupported_claims:`, `evidence_quality:` o `instruction_compliance_risk:`. `test_prompt_contracts.py` verifica que reviewer/review-prompt declaran el contrato y que implementer/implement-prompt usan `NOT_VERIFIED`.
- Riesgos pendientes: el gate valida presencia de campos, no la fuerza real de la evidencia. La calidad factual queda delegada al reviewer y a futuras tareas de telemetry/deterministic checks.

### 2026-05-27 — Tarea #10: Complexity routing S/M/L formalizado

- Cambio aplicado: `tasks.json` ahora debe incluir `complexity_reason`; el runner registra `complexity`, `complexity_reason` y pipeline elegido en logs/variables; el implementer debe copiar la ruta a `status.md` bajo `## Routing`.
- Archivos modificados:
  - `agents/structurer.md`
  - `agents/implementer.md`
  - `prompts/structure-prompt.md`
  - `prompts/consolidate-prompt.md`
  - `prompts/spec-prompt.md`
  - `prompts/plan-prompt.md`
  - `prompts/implement-prompt.md`
  - `prompts/implement-burst-prompt.md`
  - `prompts/reimplement-prompt.md`
  - `prompts/review-prompt.md`
  - `src/core/context.py`
  - `src/core/gate.py`
  - `src/harness/tasks.py`
  - `src/harness/harness_utils.py`
  - `src/mission/task_executor.py`
  - `src/mission/burst_runner.py`
  - `src/mission/hitl.py`
  - `src/tests/test_context.py`
  - `src/tests/test_gate.py`
  - `src/tests/test_harness_utils.py`
  - `src/tests/test_mission.py`
  - `src/tests/test_mission_runner.py`
  - `src/tests/test_prompt_contracts.py`
  - `src/tests/test_tasks.py`
  - `research_plan/checkpoints.md`
- Verificacion:
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-context10 src/tests/test_context.py` -> 36 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-gate10 src/tests/test_gate.py` -> 31 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-tasks10 src/tests/test_tasks.py` -> 21 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-hutils10b src/tests/test_harness_utils.py -k "task_info or render_prompt or self_verification or regrounding or signature"` -> 13 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-contract10 src/tests/test_prompt_contracts.py` -> 4 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-mission10b src/tests/test_mission.py -k "task_pipeline or check_gate or phase_runner_run_overrides"` -> 22 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-hitl10 src/tests/test_mission_runner.py -k "commit_task or wait_approval or hitl_review_loop or run_reimplement"` -> 18 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-runner10b src/tests/test_mission_runner.py -k "run_implement_bursts"` -> 3 passed.
- Evidencia: `check_gate(..., "implement[1.1]")` ahora falla si `status.md` no incluye `## Routing` con `complexity_reason:`. `TaskExecutor` pasa `TASK_COMPLEXITY`, `TASK_PIPELINE` y `TASK_COMPLEXITY_REASON` a las fases, y `test_task_pipeline_logs_and_passes_complexity_reason` comprueba que el log contiene la razon de routing.
- Riesgos pendientes: tareas antiguas sin `complexity_reason` siguen funcionando con fallback explicito a ruta `M`; la calidad de la razon generada por `structurer` sigue dependiendo del agente hasta que haya validacion semantica estructurada de `tasks.json`.

### 2026-05-27 — Tarea #11: Telemetry minima + intervention logger

- Cambio aplicado: se anadio `_telemetry.jsonl` como traza minima de mision con eventos `phase_result`, `task_started`, `task_completed`, `task_failed` e `intervention`. El esquema queda documentado en `research_plan/telemetry_schema.md`.
- Archivos modificados:
  - `src/harness/telemetry.py`
  - `src/harness/phase_logger.py`
  - `src/mission/task_executor.py`
  - `src/mission/hitl.py`
  - `src/tests/test_telemetry.py`
  - `src/tests/test_phase_logger.py`
  - `src/tests/test_mission.py`
  - `src/tests/test_mission_runner.py`
  - `research_plan/telemetry_schema.md`
  - `research_plan/checkpoints.md`
- Verificacion:
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-telemetry11b src/tests/test_telemetry.py` -> 5 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-phaselog11b src/tests/test_phase_logger.py` -> 29 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-hitl11c src/tests/test_mission_runner.py -k "wait_approval or hitl_review_loop or commit_task or run_reimplement"` -> 18 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-mission11b src/tests/test_mission.py -k "task_pipeline or check_gate or phase_runner_run_overrides"` -> 22 passed.
- Evidencia: `_write_metric(...)` sigue escribiendo `_metrics.jsonl` y ademas emite `phase_result` con `cost.input_tokens`, `cost.output_tokens`, `cost.total_tokens`, `cost.estimated_usd` y `cost.missing_component=model_pricing`. HITL emite `intervention` para `waiting_approval`, `approve`, `reject`, `retry`, `skip`, `force_approve`, `abort` y `auto_reimplement`, con `retry_count` cuando aplica.
- Riesgos pendientes: el coste en USD queda como `null` porque falta tabla/modelo de precios; se marca explicitamente como `missing_component: model_pricing`. La tarea 12 deberia convertir esto en budget/coste visible y comparable.

### 2026-05-27 — Tarea #12: Token/cost budget como restriccion primaria

- Cambio aplicado: `generate_report(...)` agrega la telemetry de fases y emite `TOKEN/COST SUMMARY` en log/stdout; tambien inyecta la misma linea en los prompts de reporte para que `mission-report.md` incluya `Token/Cost Budget`.
- Archivos modificados:
  - `src/harness/telemetry.py`
  - `src/mission/reporting.py`
  - `prompts/report-full-prompt.md`
  - `prompts/report-plan-only-prompt.md`
  - `src/tests/test_telemetry.py`
  - `src/tests/test_mission.py`
  - `src/tests/test_prompt_contracts.py`
  - `research_plan/telemetry_schema.md`
  - `research_plan/checkpoints.md`
- Verificacion:
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-telemetry12b src/tests/test_telemetry.py` -> 8 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-report12 src/tests/test_mission.py -k "generate_report_logs_and_injects_token_cost_summary"` -> 1 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-contract12 src/tests/test_prompt_contracts.py` -> 5 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-phaselog12 src/tests/test_phase_logger.py` -> 29 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-mission12 src/tests/test_mission.py -k "consolidate_tasks or notify_result or generate_report_logs_and_injects_token_cost_summary"` -> 8 passed.
- Evidencia: `format_cost_summary(...)` reporta `phases`, `input_tokens`, `output_tokens`, `total_tokens`, `estimated_usd`, `token_budget`, `remaining_tokens`, `budget_status` y `missing_components`. Si existe `CLAUDE_HARNESS_TOKEN_BUDGET`, el resumen marca `within_budget` u `over_budget`; si no existe, muestra `token_budget=not_set`.
- Riesgos pendientes: `estimated_usd` sigue siendo `unknown` mientras no exista tabla de precios por modelo; el budget actual es informativo y visible, no bloqueante. Una tarea futura podria convertir `over_budget` en gate hard configurable.

### 2026-05-28 — Tarea #13: Deterministic check registry ligado al `spec.md`

- Cambio aplicado: `spec.md` ahora debe incluir `## Deterministic Check Registry (check_registry)` con checks `DC*` ligados a requisitos `R*`/`CA*`; el reviewer debe ejecutar o inspeccionar cada check y registrar resultados en `audit.md`.
- Archivos modificados:
  - `agents/specifier.md`
  - `agents/implementer.md`
  - `agents/reviewer.md`
  - `prompts/spec-prompt.md`
  - `prompts/implement-prompt.md`
  - `prompts/implement-burst-prompt.md`
  - `prompts/reimplement-prompt.md`
  - `prompts/review-prompt.md`
  - `src/core/gate.py`
  - `src/mission/burst_runner.py`
  - `src/tests/test_gate.py`
  - `src/tests/test_mission.py`
  - `src/tests/test_mission_runner.py`
  - `src/tests/test_prompt_contracts.py`
  - `research_plan/deterministic_check_registry.md`
  - `research_plan/checkpoints.md`
- Verificacion:
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-gate13b src/tests/test_gate.py` -> 33 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-contract13b src/tests/test_prompt_contracts.py` -> 6 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-runner13 src/tests/test_mission_runner.py -k "run_implement_bursts"` -> 3 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-mission13b src/tests/test_mission.py -k check_gate` -> 14 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-hutils13 src/tests/test_harness_utils.py -k "self_verification or regrounding or signature or render_prompt"` -> 11 passed.
- Evidencia: `check_gate(..., "spec[1.1]")` falla si falta el registry o campos `id: DC`, `requirement:`, `type:` y `expected:`. `check_gate(..., "review[1.1]")` falla si `audit.md` no incluye `### Deterministic Check Registry` con `registry_source:`, `checks_executed:`, `failed_checks:` y `not_run_checks:`.
- Riesgos pendientes: la ejecucion sigue siendo manual por reviewer/implementer, no automatizada por el runner. El siguiente salto seria un parser/runner de checks `DC*` que ejecute comandos seguros y rellene evidencia automaticamente.

### 2026-05-28 — Tarea #14: Project memory ligera por target-project

- Cambio aplicado: se anadio memoria persistente por proyecto en `$HOME/.harness-memory/<project-key>/PROJECT_MEMORY.md`, staged por mision como `$CLAUDE_HARNESS/project-memory.md`, inyectada como `PROJECT_MEMORY` en fases agenticas y sincronizada al finalizar el reporte.
- Archivos modificados:
  - `src/harness/project_memory.py`
  - `src/harness/harness_utils.py`
  - `src/core/context.py`
  - `src/mission/reporting.py`
  - `src/mission/runner.py`
  - `agents/researcher.md`
  - `agents/structurer.md`
  - `agents/griller.md`
  - `agents/specifier.md`
  - `agents/planner.md`
  - `agents/implementer.md`
  - `agents/reviewer.md`
  - `prompts/brainstorm-prompt.md`
  - `prompts/structure-prompt.md`
  - `prompts/grill-prompt.md`
  - `prompts/spec-prompt.md`
  - `prompts/plan-prompt.md`
  - `prompts/implement-prompt.md`
  - `prompts/implement-burst-prompt.md`
  - `prompts/reimplement-prompt.md`
  - `prompts/review-prompt.md`
  - `prompts/report-full-prompt.md`
  - `prompts/report-plan-only-prompt.md`
  - `src/tests/test_project_memory.py`
  - `src/tests/test_context.py`
  - `src/tests/test_mission.py`
  - `src/tests/test_mission_runner.py`
  - `src/tests/test_prompt_contracts.py`
  - `research_plan/project_memory.md`
  - `research_plan/checkpoints.md`
- Verificacion:
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-memory14 src/tests/test_project_memory.py` -> 7 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-context14 src/tests/test_context.py` -> 37 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-contract14 src/tests/test_prompt_contracts.py` -> 7 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-setup14 src/tests/test_mission.py -k "setup_harness or resolve_includes or generate_report_logs_and_injects_token_cost_summary"` -> 9 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-runner14 src/tests/test_mission_runner.py -k "generate_report_syncs_project_memory or run_implement_bursts"` -> 4 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-hutils14 src/tests/test_harness_utils.py -k "render_prompt or signature or regrounding or self_verification"` -> 11 passed.
- Evidencia: `setup_harness(...)` crea/copia `project-memory.md` y `_project_memory_path`; `sync_project_memory(...)` copia cambios del harness al persistente tras `generate_report`; `PHASE_REGISTRY` inyecta `PROJECT_MEMORY` en research, structure, grill, spec, plan, implement, implement_bursts, review y reimplement.
- Riesgos pendientes: la actualizacion semantica de memoria depende del reporte final; no hay deduplicacion automatica ni retrieval por similitud. Eso corresponde mejor a la tarea 15.

### 2026-05-28 — Tarea #15: Mission case base persistente

- Cambio aplicado: se anadio `cases.jsonl` por proyecto con misiones aprobadas, recuperacion lexical top-k y staging de `$CLAUDE_HARNESS/retrieved-cases.md` como `MISSION_CASES` para fases agenticas.
- Archivos modificados:
  - `src/harness/case_base.py`
  - `src/harness/harness_utils.py`
  - `src/core/context.py`
  - `src/cli.py`
  - `src/mission/runner.py`
  - `agents/researcher.md`
  - `agents/structurer.md`
  - `agents/griller.md`
  - `agents/specifier.md`
  - `agents/planner.md`
  - `agents/implementer.md`
  - `agents/reviewer.md`
  - `prompts/brainstorm-prompt.md`
  - `prompts/structure-prompt.md`
  - `prompts/grill-prompt.md`
  - `prompts/spec-prompt.md`
  - `prompts/plan-prompt.md`
  - `prompts/implement-prompt.md`
  - `prompts/implement-burst-prompt.md`
  - `prompts/reimplement-prompt.md`
  - `prompts/review-prompt.md`
  - `src/tests/test_case_base.py`
  - `src/tests/test_context.py`
  - `src/tests/test_mission.py`
  - `src/tests/test_mission_runner.py`
  - `src/tests/test_prompt_contracts.py`
  - `research_plan/mission_case_base.md`
  - `research_plan/checkpoints.md`
- Verificacion:
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-case15 src/tests/test_case_base.py` -> 8 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-memory15 src/tests/test_project_memory.py` -> 7 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-context15 src/tests/test_context.py` -> 38 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-contract15b src/tests/test_prompt_contracts.py` -> 8 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-setup15 src/tests/test_mission.py -k "setup_harness or resolve_includes or generate_report_logs_and_injects_token_cost_summary"` -> 9 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-runner15b src/tests/test_mission_runner.py -k "generate_report_saves_approved_mission_case or generate_report_syncs_project_memory or run_implement_bursts"` -> 5 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-hutils15 src/tests/test_harness_utils.py -k "render_prompt or signature or regrounding or self_verification"` -> 11 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-mission15b src/tests/test_mission.py -k "task_pipeline or check_gate or phase_runner_run_overrides"` -> 22 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-tasks15 src/tests/test_tasks.py` -> 21 passed.
- Evidencia: `stage_retrieved_cases(...)` escribe `retrieved-cases.md` y `_project_cases_path`; `retrieve_cases(...)` recupera por solapamiento lexical normalizado; `save_approved_mission_case(...)` solo guarda si no hay bloqueo, `tasks.json` esta completo y `audit.md` es `APPROVED` o no existe.
- Riesgos pendientes: la similitud es lexical simple, no BM25/vectorial; la calidad mejora cuando haya suficientes casos reales. Una evolucion futura podria deduplicar semanticamente y seleccionar demonstrations con metrica.

### 2026-05-28 - Tarea #16: Skill library post-mision

- Cambio aplicado: se anadio una skill library persistente por proyecto en `$HOME/.harness-memory/<project-key>/skills/`, con indice `skills.jsonl`, retrieval a `$CLAUDE_HARNESS/retrieved-skills.md`, bandeja post-mision `$CLAUDE_HARNESS/generated-skills/` y skill semilla `prompt-gate-contract-change`.
- Archivos modificados:
  - `src/harness/skill_library.py`
  - `src/harness/harness_utils.py`
  - `src/core/context.py`
  - `src/mission/reporting.py`
  - `src/mission/runner.py`
  - `agents/researcher.md`
  - `agents/structurer.md`
  - `agents/griller.md`
  - `agents/specifier.md`
  - `agents/planner.md`
  - `agents/implementer.md`
  - `agents/reviewer.md`
  - `prompts/brainstorm-prompt.md`
  - `prompts/structure-prompt.md`
  - `prompts/grill-prompt.md`
  - `prompts/spec-prompt.md`
  - `prompts/plan-prompt.md`
  - `prompts/implement-prompt.md`
  - `prompts/implement-burst-prompt.md`
  - `prompts/reimplement-prompt.md`
  - `prompts/review-prompt.md`
  - `prompts/report-full-prompt.md`
  - `prompts/report-plan-only-prompt.md`
  - `src/tests/test_skill_library.py`
  - `src/tests/test_context.py`
  - `src/tests/test_mission.py`
  - `src/tests/test_mission_runner.py`
  - `src/tests/test_prompt_contracts.py`
  - `research_plan/skill_library.md`
  - `research_plan/checkpoints.md`
- Verificacion:
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-skill16 src/tests/test_skill_library.py` -> 5 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-context16 src/tests/test_context.py` -> 39 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-contract16 src/tests/test_prompt_contracts.py` -> 9 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-setup16 src/tests/test_mission.py -k "setup_harness or resolve_includes or generate_report_logs_and_injects_token_cost_summary"` -> 9 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-runner16 src/tests/test_mission_runner.py -k "generate_report_syncs_project_memory or generate_report_saves_approved_mission_case or generate_report_syncs_generated_skills or run_implement_bursts"` -> 6 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-hutils16 src/tests/test_harness_utils.py -k "render_prompt or signature or regrounding or self_verification"` -> 11 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-case16 src/tests/test_case_base.py` -> 8 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-memory16 src/tests/test_project_memory.py` -> 7 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-mission16 src/tests/test_mission.py -k "task_pipeline or check_gate or phase_runner_run_overrides"` -> 22 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-tasks16 src/tests/test_tasks.py` -> 21 passed.
  - `git diff --check` -> clean, only CRLF warnings.
- Evidencia: `stage_retrieved_skills(...)` crea `retrieved-skills.md`, `_project_skills_path` y `generated-skills/`; `retrieve_skills(...)` recupera la skill semilla por triggers de contrato prompt/gate; `sync_generated_skills(...)` promociona solo skills con `status: verified` e indexa su metadata.
- Riesgos pendientes: la recuperacion es lexical simple y la calidad de nuevas skills depende del reporte final; el runner valida `status: verified`, pero no audita semanticamente si la skill nueva es realmente util o no duplicada salvo por `skill_id`.

### 2026-05-28 - Tarea #17: Refiner post-mision con aprobacion humana

- Cambio aplicado: se anadio un refiner offline que genera `$CLAUDE_HARNESS/refiner-proposal.md` desde firmas de fallo recurrentes, con `approval_required: true` y `auto_apply: false`. El proceso propone cambios a prompts/agentes pero no los aplica.
- Archivos modificados:
  - `src/harness/refiner.py`
  - `src/harness/harness_utils.py`
  - `prompts/refiner-prompt.md`
  - `commands/refine-harness.md`
  - `AGENTS.md`
  - `src/tests/test_refiner.py`
  - `src/tests/test_prompt_contracts.py`
  - `research_plan/refiner_post_mission.md`
  - `research_plan/checkpoints.md`
- Verificacion:
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-refiner17 src/tests/test_refiner.py` -> 6 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-contract17 src/tests/test_prompt_contracts.py` -> 10 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-hutils17 src/tests/test_harness_utils.py -k "render_prompt or signature or refiner or task_info"` -> 10 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-case17 src/tests/test_case_base.py` -> 8 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-telemetry17 src/tests/test_telemetry.py` -> 8 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-mission17 src/tests/test_mission.py -k "setup_harness or resolve_includes or task_pipeline or check_gate"` -> 29 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-runner17 src/tests/test_mission_runner.py -k "generate_report or run_implement_bursts or wait_approval"` -> 13 passed.
- Evidencia: `collect_failure_signals(...)` extrae `failure_type@recoverability_lost_at_stage` desde `audit.md`, telemetry y `cases.jsonl`; `build_refiner_proposal(...)` solo propone cambios cuando una firma alcanza recurrencia; `write_refiner_proposal(...)` escribe unicamente `refiner-proposal.md`.
- Riesgos pendientes: la recurrencia es estructural/lexical, no semantica; una firma repetida puede ser incidental. Por eso la aprobacion humana sigue siendo obligatoria y el refiner no genera patches.

### 2026-05-28 - Tarea #18: Partial harness mode

- Cambio aplicado: se anadieron modos parciales `spec` y `spec-plan`; el task loop completa artefactos parciales sin implementar, revisar, stagear ni mergear. El alias duplicado `plan` fue retirado tras confirmar que ejecutaba el mismo pipeline que `spec-plan`.
- Archivos modificados:
  - `src/core/context.py`
  - `src/mission/task_executor.py`
  - `src/cli.py`
  - `prompts/report-plan-only-prompt.md`
  - `docs/system-spec.md`
  - `src/tests/test_context.py`
  - `src/tests/test_mission.py`
  - `src/tests/test_mission_runner.py`
  - `src/tests/test_prompt_contracts.py`
  - `research_plan/partial_harness_mode.md`
  - `research_plan/checkpoints.md`
- Verificacion:
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-partial18-context src/tests/test_context.py` -> 44 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-partial18-mission src/tests/test_mission.py -k "parse_args or mode_spec or spec_mode or spec_plan or partial_task_pipeline or finalize_partial_modes_no_merge or task_pipeline_plan_mode_overrides_complexity"` -> 28 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-partial18-runner src/tests/test_mission_runner.py -k "run_finalize_no_merge_mode or execute_explore_mode_skips_task_loop"` -> 2 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-partial18-contract src/tests/test_prompt_contracts.py` -> 11 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-partial18-mission-full src/tests/test_mission.py` -> 177 passed.
  - `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest-codex-basetemp-partial18-runner-full src/tests/test_mission_runner.py` -> 37 passed.
  - `git diff --check` -> clean, only CRLF warnings.
- Evidencia: `MISSION_PIPELINES` expone `spec` y `spec-plan`; `PARTIAL_TASK_PIPELINES` fuerza `spec` o `spec -> plan` ignorando S/M/L; `TaskExecutor` usa `is_partial_harness_mode()` para marcar la tarea completada tras los artefactos parciales y evita `stage_task_files`/`commit_task`; la CLI acepta `--spec-only`, `--spec-plan`, `--mode spec` y `--mode spec-plan`.
- Riesgos pendientes: el benchmark aun requiere ejecuciones reales comparativas para medir calidad/coste de `spec` vs `spec-plan` vs `full`; el modo parcial produce artefactos y telemetry, pero no evalua automaticamente su calidad semantica.

```text
### YYYY-MM-DD — Tarea #N: nombre

- Cambio aplicado:
- Archivos modificados:
- Verificación:
- Evidencia:
- Riesgos pendientes:
```

---

## 3. Decisiones abiertas

| Estado | Decisión | Contexto |
|--------|----------|----------|
| `[x]` | Elegir si los checks se registran solo en este Markdown o también en `tasks.json`. | Elegido `spec.md` Markdown por ahora: `## Deterministic Check Registry`; JSON queda reservado para una automatizacion futura. |
| `[x]` | Decidir si la telemetry mínima vive en `status.md`, `audit.md` o JSONL separado. | Elegido JSONL separado: `$CLAUDE_HARNESS/_telemetry.jsonl`, para evitar mezclar trazas con artefactos semanticos. |
| `[ ]` | Definir qué tareas entran en el primer paquete MVP. | Recomendación actual: tareas 1 a 6. |

---

## 4. Propuesta de proceso

Usar este archivo como **ledger humano** y no como sistema automatizado todavía.

Proceso recomendado:

1. Antes de empezar una mejora, cambiar su estado a `[~]`.
2. Al terminar, marcar `[x]` solo si hay verificación mínima.
3. Añadir entrada en "Registro de checkpoints completados".
4. Si aparece una decisión de diseño, registrarla en "Decisiones abiertas" o cerrarla con una nota.
5. Cuando haya varias tareas completadas, considerar migrar el estado a `tasks.json` o JSONL para reporting automático.

Por ahora, Markdown gana: es barato, claro, versionable y suficiente para no perder el hilo.
