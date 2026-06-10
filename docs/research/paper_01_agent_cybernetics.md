# Paper 01 — Agent Cybernetics is the Missing Science of Foundation Agents

**Autores:** Xinrun Wang, Chang Yang, He Zhao, Zhuoyi Lin, Shuyue Hu (SMU, PolyU, NTU, A*STAR, Shanghai AI Lab)
**arXiv:** 2605.10754v1, mayo 2026
**Tipo:** Position paper / framework teórico (NO empírico)
**Fichero:** `papers/agent cybernetics is the missing science of fundation agents.pdf`

---

## 1. Tesis del paper en una frase

La cibernética clásica (Wiener, Ashby, Shannon, von Foerster) proporciona el andamiaje teórico que falta en el diseño de foundation agents. Los autores mapean **6 leyes cibernéticas** a **6 principios de diseño de agentes**, y los sintetizan en **3 desiderata de ingeniería** (Reliability, Lifelong Running, Self-Improvement).

No hay experimentos. No hay benchmark. Es prescriptivo: te dice qué deberías construir, no demuestra que funcione.

---

## 2. Los 6 principios (resumen operativo)

| # | Principio | Cibernética | Implicación práctica |
|---|-----------|-------------|----------------------|
| P1 | Closed-Loop Feedback | Feedback negativo | El resultado de cada tool call debe re-inyectarse de forma que **fuerce** al agente a reconocerlo antes de actuar. Combate la "feedback blindness". |
| P2 | Requisite Variety | Ley de Ashby | Variedad output × variedad interna ≥ variedad del entorno. La capacidad real está acotada por el mínimo de las dos. |
| P3 | Goal Homeostasis & Adaptive Re-Anchoring | Ultraestabilidad | Dos loops: uno rápido que mantiene el objetivo dentro de su región viable, otro lento que **reformula el objetivo** cuando el primero falla N veces. |
| P4 | Black-Box Environment Modelling | Caja negra de Ashby | Tratar todo conocimiento previo como hipótesis falsable. Probar con acciones baratas antes de comprometerse. |
| P5 | Second-Order Regulation | Cibernética de segundo orden | El agente monitoriza **su propio razonamiento**: loops, drift, confianza miscalibrada. Escala a humano cuando detecta degradación. |
| P6 | Context Entropy Minimization | Capacidad de canal de Shannon | El contexto es un canal finito. Sólo retener tokens cuyo **mutual information** con la decisión correcta supere un umbral. |

---

## 3. Recomendaciones específicas para code generation

El paper dedica una sección (5.1) a code-gen. Tres recomendaciones operativas:

- **R-CG1 (P1):** Antes de cualquier edición posterior a un test fallido, el agente debe escribir un bloque `[diagnosis]` con índice del test fallado, root cause y plan de fix. Ediciones **sin** `[diagnosis]` son rechazadas por el harness.
- **R-CG2 (P3):** Cada k≈20-50 pasos, inyectar un `GoalState` con clasificación `DONE / IN-PROGRESS / NOT-STARTED / BROKEN`. Si m checkpoints reportan los mismos invariantes BROKEN, disparar **reformulación del objetivo** (outer loop) en vez de seguir editando.
- **R-CG3 (P5/P6):** Gate de auto-consistencia pre-commit (contratos de interfaz, call sites, markers sin resolver). Promover patrones a una **skill library** sólo tras validarlos en ≥2 instancias held-out.

---

## 4. Qué adoptamos en HERO y cómo está implementado

Los principios cibernéticos de este paper se materializan en HERO de forma concreta:

### P1 — Closed-loop feedback + diagnosis gate (R-CG1)
- **Del paper:** toda edición posterior a un fallo debe ir precedida de un bloque `[diagnosis]` con root cause; las ediciones sin diagnóstico se rechazan para combatir la *feedback blindness*.
- **En HERO:** la fase `REIMPLEMENT` exige una sección `## Diagnosis` que el gate valida antes de aceptar el trabajo (`GATE_REQUIRED_MARKERS` en `src/core/gate.py`). El veredicto del reviewer (`audit.md`) se re-inyecta en `REIMPLEMENT` como artefacto de entrada (`PHASE_REGISTRY` en `src/core/context.py`; orquestación en `src/mission/hitl.py`), cerrando el loop reviewer → reimplement.

### P2 — Requisite variety: herramientas por fase
- **Del paper:** la variedad interna del agente debe igualar la del entorno; ni más ni menos.
- **En HERO:** cada fase recibe un conjunto de herramientas acotado a su función vía `DEFAULT_TOOLS`, `IMPL_TOOLS` y `REVIEW_TOOLS` (`src/core/context.py`). El reviewer no tiene `Edit` (no puede tocar código); el implementer sí.

### P3 — Goal homeostasis: estado explícito y re-anclaje del objetivo
- **Del paper:** mantener el objetivo dentro de su región viable y re-inyectarlo periódicamente para evitar *goal drift*.
- **En HERO:** `spec.md` se re-inyecta en cada burst de implementación (`run_implement_bursts` en `src/mission/burst_runner.py`), y el gate exige un marcador `STATUS: DONE | BLOCKED` al cierre de `status.md` (`src/core/gate.py`).

### P5 — Second-order regulation: auto-verificación y refiner offline
- **Del paper:** el agente debe monitorizar su propio razonamiento y escalar cuando detecta degradación.
- **En HERO:** las fases `IMPLEMENT`/`REIMPLEMENT` exigen una sección `## Self-Verification` validada por el gate (`src/core/gate.py`, contrato en `agents/implementer.md`). Fuera del loop, el **refiner post-misión** (`src/harness/refiner.py`) detecta firmas de fallo recurrentes (`failure_type@stage`, recurrencia ≥ 2) a partir de `_telemetry.jsonl` y **propone** mejoras sin aplicarlas. El control de bucles se realiza vía HITL (`src/mission/hitl.py`: retry/skip/abort).

### P6 — Context entropy minimization: compactación hot → cold
- **Del paper:** el contexto es un canal finito; retener solo lo que aporta información a la decisión.
- **En HERO:** la pizarra `context-hot.md` se compacta a `context-cold.md` tras cada tarea (`compact_context` + fase `COMPACT` + `prompts/compact-prompt.md`). La compactación es **basada en contenido** (un resumen producido por el modelo que preserva paths, patrones y gotchas), no ponderada por información mutua.

### Soporte adicional alineado con el paper
- **Code graph como sonda del entorno (P4):** `src/analysis/` construye un grafo de dependencias con tree-sitter (`builder.py`, `code_graph.py`: `dependents`, `impact-analysis`).
- **Skill library (R-CG3):** `src/harness/skill_library.py` persiste y recupera skills por similitud léxica (`retrieved-skills.md`).

## 5. No adoptado (y por qué)

- **Compactación ponderada por información mutua (P6 ideal):** la compactación es por resumen de contenido, no por *mutual information*. Formalizarla requeriría un benchmark propio para definir qué información predice acciones futuras.
- **Detección de bucles en tiempo real (P5):** no hay un detector automático que reconozca que el agente repite la misma edición; el control de bucles es vía HITL y el refiner offline.
- **Reformulación del objetivo en outer-loop tras *m* fallos:** no existe como lógica automática del runner; es un patrón de investigación más amplio.
