# Auditoria evidence-anchored vs instruction-compliance

**Fecha:** 2026-05-27  
**Checkpoint:** tarea 9  
**Objetivo:** detectar instrucciones que podian inducir cumplimiento superficial y ajustarlas para exigir evidencia concreta.

## Criterio usado

- **Evidence-anchored:** la regla obliga a citar `archivo:linea`, comando/test con resultado, validacion, requisito del spec o comportamiento observado.
- **Instruction-compliance risk:** la regla puede producir una marca de cumplimiento sin demostrar que el resultado sea correcto.
- **Ajuste aplicado:** cambio minimo en agente/prompt para convertir claims en evidencia verificable.

## Tabla de auditoria

| Artefacto | Regla revisada | Clasificacion | Riesgo | Ajuste aplicado |
|---|---|---|---|---|
| `agents/implementer.md` | Actualizar `status.md` marcando pasos completados. | Instruction-compliance risk | El implementer podia marcar un paso como hecho solo por haber seguido el plan. | Se anadio `## Disciplina evidence-anchored`: cada paso completado necesita comando, test, `archivo:linea`, criterio o comportamiento observado; si no, `NOT_VERIFIED: razon`. |
| `prompts/implement-prompt.md` | Escribir `## Self-Verification`. | Instruction-compliance risk | La seccion podia convertirse en ceremonia sin evidencia. | Cada campo de self-verification exige comando/resultado, criterio + evidencia, paths concretos o razon `NOT_APPLICABLE`/`NOT_RUN`. |
| `prompts/reimplement-prompt.md` | Escribir `## Diagnosis` y `## Self-Verification`. | Mixed | El retry podia cumplir formato sin demostrar que corrigio el fallo. | Se anadio `## Evidence anchoring`: cada fix necesita audit line, test, comando, `file:line`, criterio o comportamiento observado. |
| `agents/reviewer.md` | Aprobar si status/checkpoints parecen completos. | Instruction-compliance risk | El reviewer podia confiar en claims del implementer. | Se anadio auditoria de evidence anchoring: `status.md`, self-verification y checkboxes son claims; claims materiales sin evidencia se registran como `unsupported_claim` y bloquean aprobacion si afectan correccion. |
| `prompts/review-prompt.md` | Review contra spec y plan. | Evidence-anchored reforzado | Faltaba una seccion explicita para evaluar claims no soportados. | `audit.md` debe incluir `### Evidence Anchoring (evidence_anchoring)` con `unsupported_claims`, `evidence_quality` e `instruction_compliance_risk`. |
| `agents/specifier.md` | Crear criterios de aceptacion verificables. | Mixed | El spec podia incluir buenas practicas genericas no pedidas. | Cada requisito/criterio debe anclarse en usuario, brief, codigo/test existente o edge case observado; inferencias deben etiquetarse. |
| `agents/specifier.md` | Emitir `STATUS: ALREADY_DONE`. | Instruction-compliance risk | La tarea podia darse por resuelta con una frase de justificacion sin prueba. | `ALREADY_DONE` ahora exige evidencia concreta (`archivo:linea` y test/comando si aplica). |
| `prompts/spec-prompt.md` | Generar requisitos y acceptance criteria. | Mixed | Riesgo de inflar criterios por sonar completos. | Se anadio bloque `Evidence anchoring` para prohibir requisitos genericos sin evidencia. |
| `agents/planner.md` | Crear pasos de implementacion y verificacion. | Mixed | El plan podia incluir pasos de diligencia no conectados al problema. | Cada paso debe estar motivado por spec, ADR, path de codigo o riesgo observado; verification distingue checks ejecutables/manuales y su evidencia esperada. |
| `prompts/plan-prompt.md` | Plan corto orientado a interfaces. | Evidence-anchored reforzado | Podia omitir por que un paso existe. | Cada paso debe declarar anclaje y evidencia esperada. |
| `prompts/implement-burst-prompt.md` | Registrar progreso por burst. | Instruction-compliance risk | `_burst_progress.md` podia ser un resumen sin evidencia. | El resumen de burst debe incluir comando, test, `file:line` o comportamiento observado; si no, `NOT_VERIFIED`. |

## Resultado

El harness ahora distingue:

- **claim:** "he completado/verificado/cumplido X";
- **evidence:** prueba concreta que permite al reviewer comprobar X;
- **unsupported_claim:** claim material sin prueba suficiente.

Este cambio reduce el riesgo de que los agentes optimicen por obedecer el formato visible en vez de resolver la tarea con evidencia.
