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

## 4. Mapeo a nuestro harness (qué tenemos vs qué falta)

| Principio | Cobertura actual | Gap concreto |
|-----------|------------------|--------------|
| P1 Closed-loop | ✅ reviewer + reimplement loop, `audit.md` se re-inyecta en REIMPLEMENT con la instrucción "fix ONLY what the reviewer flagged" | ⚠️ No exige un bloque `[diagnosis]` explícito. El reimplementer puede arreglar sin verbalizar root cause. **Feedback blindness** sigue posible en silencio. |
| P2 Requisite variety | Parcial: `tools` se configuran por fase (DEFAULT, IMPL_TOOLS, REVIEW_TOOLS) | No hay métrica formal de variedad. Probablemente innecesario formalizar. |
| P3 Goal homeostasis | Parcial: `grill` produce `brief.md` que sí entra en cada fase; `spec.md` se incluye en plan/implement/review | ❌ En IMPLEMENT_BURSTS no se re-inyecta `spec.md` entre bursts. **Goal drift** plausible en tareas L con muchos pasos. ❌ No hay clasificación DONE/IN-PROGRESS/BROKEN explícita en `status.md`. ❌ No hay disparador de "outer loop reformulation" tras m fallos. |
| P4 Black-box | Parcial: `build_code_graph` es una sonda al entorno | No hay modelo del entorno externo (APIs, sistema de ficheros). El agente asume comportamiento de tools. |
| P5 Second-order | Parcial: reviewer externo. HITL escala a humano | ❌ El agente no detecta su propio looping. Si el implementer hace 5 ediciones que rotan sobre el mismo bug, no hay detector. ❌ No hay calibración de confianza propia. |
| P6 Context entropy min | Parcial: hot/cold con compactación tras cada tarea | ⚠️ La compactación es **por bytes**, no por mutual information. El paper articula exactamente la crítica que ya hicimos en sesión previa. |

---

## 5. Análisis Riesgo · Beneficio · Impacto · Novedad

### 5.1 Como aporte al **harness** (implementación)

| Recomendación | Coste (Riesgo) | Beneficio | Impacto | Novedad |
|---------------|----------------|-----------|---------|---------|
| **Diagnosis gate (R-CG1)** en REIMPLEMENT | Bajo. Editar `reimplement-prompt.md` + añadir validador en gate | Alto. Combate feedback blindness, que es el fallo dominante en bug-fix iterativo | Alto sobre tareas con audit rechazado | Baja (ya lo hacen muchos harnesses, p.ej. Aider) |
| **Spec re-injection en bursts (R-CG2 inner)** | Bajo-Medio. Tocar `burst_runner.py` para inyectar `spec.md` cada N pasos | Alto en tareas L con muchos bursts. Mitiga goal drift | Medio (sólo afecta complexity=L) | Baja |
| **GoalState explícito en `status.md`** (R-CG2 parte 1) | Medio. Cambia formato de status; reviewer debe parsearlo; tests | Medio. Hace progreso explícito | Medio | Media (la mayoría de harnesses no formalizan esto) |
| **Outer-loop reformulation tras m audits fallidos** (R-CG2 parte 2) | Medio-Alto. Lógica nueva en `HitlReviewer` + un agente "reformulator" o re-grill | Alto si tienes tareas que entran en loops largos de retry | Bajo (raro que pase N>3 retries antes de /skip) | Alta — pocos harnesses tienen esto formalizado |
| **MI-weighted compaction (P6)** | Alto. Requiere benchmark previo para validar qué información predice acciones futuras | Incierto. Suena bien, no hay evidencia | Medio | Alta como contribución de research |
| **Self-loop detection (P5)** | Medio. Heurística sobre diffs de status.md entre intentos | Medio. Cubre el "el implementer hace lo mismo 5 veces" | Medio | Media |
| **Skill library promocionada automáticamente (R-CG3)** | Muy alto. Memoria persistente fuera del workspace efímero, política de promoción, validación en held-out | Alto a largo plazo, nulo a corto | Bajo (sólo importa tras N misiones) | Media (Voyager ya lo hace) |

### 5.2 Como aporte al **paper / benchmark**

| Dimensión | Valoración |
|-----------|------------|
| **Útil como marco teórico para citar** | **Alto.** Da vocabulario riguroso (feedback blindness, goal drift, variety, second-order regulation, channel capacity) para describir lo que nuestro harness hace y por qué. |
| **Útil como predicción a falsar** | **Alto.** El paper hace afirmaciones específicas (p.ej. "feedback-blindness es el bottleneck dominante en code-gen"). Nuestro benchmark puede testar si harness con R-CG1 supera harness sin R-CG1. |
| **Útil como SOTA contra el que posicionarse** | **Medio.** No es comparable: es teórico, no empírico. Citarlo refuerza la narrativa "implementamos y medimos lo que ellos sólo postulan". |
| **Riesgo de over-claim** | **Medio.** El paper es ambicioso pero no aporta evidencia. Si lo citamos como "scientific foundation", debemos ser explícitos en que es un position paper. |

---

## 6. Decisiones recomendadas

### Si queremos enriquecer el **harness** (prioridad por ratio impacto/coste):

1. **R-CG1 (Diagnosis gate)** — sí, primera incorporación. Pequeño, defendible, directamente medible: con/sin diagnosis, ¿mejora el pass rate tras reimplement?
2. **Spec re-injection en bursts** — sí, segunda. Cambio quirúrgico en `burst_runner.py`. Defendible empíricamente.
3. **Self-loop detection (P5)** — explorar tras MVP. Implementable como heurística sobre history de status.md.
4. **Outer-loop reformulation** — investigar como skill nuevo, no como parte del runner. Es un patrón de research más grande.
5. **MI-weighted compaction** — fuera del MVP. Requiere su propio mini-benchmark para definir qué es "información útil".
6. **Skill library automatizada** — fuera del scope. Voyager/continual-harness ya lo cubren mejor.

### Si queremos enriquecer el **paper**:

- **Citar como theoretical framing** en la sección de fundamentos. Útil para describir las hipótesis (H1-H5) en lenguaje de cibernética.
- **No tratar como SOTA empírico** — el paper no compite con SWE-bench ni con nuestro benchmark. Es complementario.
- **Posible hipótesis derivada (opcional):** H6 — "Un harness con diagnosis gate (R-CG1) reduce el número de retries necesarios para llegar a APPROVED frente a uno sin él". Sería un experimento ablativo dentro del propio harness, independiente del benchmark principal.

---

## 7. Veredicto franco

- **Como teoría:** sólida y bien articulada. Da vocabulario que el campo necesita. La mayoría de sus afirmaciones son razonables aunque algunas son retóricas (mapear cibernética a LLMs tiene tirón, pero el paralelo Shannon ↔ context window es más analogía que teorema operativo).
- **Como guía de ingeniería:** las 3 recomendaciones de code-gen son concretas y aplicables. R-CG1 es la fruta colgada baja.
- **Riesgo de adoptar todo:** alto si lo tratamos como religión. Bajo si extraemos las 2-3 cosas pequeñas que son baratas y medibles.
- **Honestamente:** el paper sería más fuerte con un solo experimento. La ausencia de validación empírica es su mayor debilidad — y es exactamente el hueco que **nuestro** benchmark puede llenar parcialmente.

**Acción concreta sugerida:** anotar **R-CG1 (diagnosis gate)** como candidato a implementar y benchmarkear como sub-experimento del paper propio, antes de invertir en cualquier otra recomendación.
