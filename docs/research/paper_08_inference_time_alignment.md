# Paper 08 — Harnesses for Inference-Time Alignment over Execution Trajectories

- **Autores**: Boyuan Wang, Bochao Li, Minghan Wang, Yuxin Tao, Fang Kong (Southern University of Science and Technology, China).
- **ArXiv**: 2605.21516v1 — Mayo 2026.
- **Tipo**: Teórico-formal con validación empírica (synthetic + TerminalBench v2).
- **Archivo**: `papers/harnesses for inference-time alingment over execution trajectories.pdf`.

---

## Tesis en una frase

> Diseñar un harness es un **problema de alineación inference-time** entre lo que pide la estructura humana y lo que el agente puede realizar; **más estructura no siempre es mejor**, y **harnesses parciales (que solo prescriben los pasos iniciales y liberan al agente después) pueden superar a workflows completamente especificados**.

---

## Piezas operativas clave

### Marco formal — descomposición de harness en (κ, λ, ψ)

| Parámetro | Significado | Timescale | Análogo nuestro |
|---|---|---|---|
| **κ (kappa)** | Granularidad de descomposición — cuántos sub-goals genera el plan | Outer (harness) | `plan.md` → checkpoints/tasks |
| **λ (lambda)** | Fuerza del guidance — cuánto reshape la distribución del agente | Inner (per-stage) | Prescripción detallada en spec/plan vs. dejar al implementer |
| **ψ (psi)** | Regla local de guidance — qué trayectorias prefiere | Inner | "Reglas de oro" en agents/*.md, definitions of done |

### Tres principios de alineación

#### **P1 — Granularity-Capability Alignment** (Teorema 1)
- Cada stage pide progreso latente $\ell_t$ con presupuesto de $M_t$ pasos.
- Penalización $\rho_t^{(M_t)}$: cuadrática en el gap entre $\ell_t$ y lo realizable.
- **Implicación**: la granularidad óptima **no se decide contra la estructura lógica de la tarea**, sino **contra la dinámica de ejecución del agente**. Stages demasiado finos colapsan; demasiado gruesos quedan irrecuperables.

#### **P2 — Guidance-Evidence Alignment** (Teorema 2)
- Retention gap $\Gamma_{t,\lambda_t}$: log-diferencia entre peso sobre trayectorias recuperables vs. no recuperables.
- **Guidance sube** stage success **solo si Γ > 0**. Si Γ < 0, **amplifica** alucinación.
- **Implicación**: subir λ (más guidance) **amplifica el signo de ψ**. Si tu regla guidance favorece "compliance con instrucción sin chequear evidencia", **subir intensidad empeora el resultado** (hallucinated execution).

#### **P3 — Partial Harnessing** (regla marginal de parada)
- Añadir un stage tiene **doble efecto**: reduce tail-risk pero impone otro constraint de recoverability.
- Existe un m* óptimo donde el harness debe **parar de especificar** y entregar al agente.
- **Hallazgo empírico**: harness parciales (solo prefijo inicial especificado) baten a workflows full-coverage en TerminalBench v2 y synthetic tasks.

### Modos de fallo identificados explícitamente
1. **Over-decomposition** — sub-goals demasiado finos, el agente no puede "parar limpio" en cada milestone.
2. **Over-pruning** — guidance excesivo elimina trayectorias recuperables.
3. **Hallucinated execution** — ψ premia compliance sobre evidencia, λ amplifica → alucinación.

---

## Mapeo a nuestro harness

| Concepto del paper | Nuestro estado | Diagnóstico |
|---|---|---|
| **κ — granularidad** | Tres tamaños fijos: S=[IMPLEMENT], M=[SPEC,PLAN,IMPLEMENT,REVIEW], L=[..., bursts] | **Granularidad por complejidad de tarea, NO por capacidad del modelo**. P1 dice que esto está mal: la granularidad correcta depende del agente, no solo de la tarea |
| **λ — fuerza del guidance** | Implícita; nuestros prompts son densos y prescriptivos | **Riesgo alto P2**: si ψ favorece "follow the spec" sin chequear evidencia → amplifica alucinación |
| **ψ — regla guidance** | `agents/*.md` contiene reglas duras, checks de outcome, formato | Mezcla evidence-based (CHECKPOINTS) y instruction-compliance (formato, fases) — **mezcla puede ser óptima** |
| **Partial harnessing** | Modo `explore` se aproxima (sin spec/plan); modo `full` es full harness | **Ya practicamos parcialmente**, pero sin formalizarlo. P3 nos da fundamento teórico |
| **Recoverability tubes** | HITL como rescate; reviewer como gate | Nuestro HITL **es** un mecanismo de recovery cuando un prefix se vuelve no-recoverable |
| **Stagewise product de probs** | M-HIR (paper 03) mide proxy de stage failures | Compatible con framework |

---

## Aplicabilidad

### Para el harness

| Acción | Coste | Beneficio | Impacto | Novedad |
|---|---|---|---|---|
| **Adoptar formalmente "Partial Harnessing"** como modo: spec inicial + agente libre tras checkpoint N | Medio (nuevo modo en `MISSION_PIPELINES`) | **Alto** — evidencia empírica de superioridad en TerminalBench | Alto | Alta (Mayo 2026, idea fresca) |
| **Capability-aware granularity** — elegir S/M/L según modelo, no solo complejidad de tarea | Bajo (parametrizar `TASK_PIPELINES` por modelo) | Medio — P1 lo predice, paper 05 ya lo confirmó | Medio-alto | Media |
| **Auditar ψ de cada agent prompt**: ¿premia evidence-checking o instruction-compliance? | Bajo (revisión textual de `agents/*.md`) | **Alto** — P2 dice que mezcla mal-calibrada genera alucinación | Alto | Media |
| Marginal stopping rule en HITL: detectar cuándo agregar más checkpoints empeora | Alto (instrumentación) | Medio | Medio | Alta |
| Métrica **retention gap** Γ aproximada — comparar tasa-de-éxito-de-stage con vs. sin guidance específico | Alto | Medio | Alto en research, bajo en práctica | Alta |

### Para el paper

| Uso | Coste | Beneficio | Impacto | Novedad |
|---|---|---|---|---|
| **Cita teórica obligatoria** — provee fundamento formal para "más estructura no es mejor" | Trivial | **Crítico** | Alto | Alta |
| Adoptar nomenclatura (κ, λ, ψ) en sección de framework | Bajo | Alto — vocabulario aceptable por reviewers teóricos | Alto | Media |
| Reframe de nuestros 5 modos (full/focused/plan/explore/hotfix) como **puntos en el espacio (κ, m)** | Medio | Alto — narrativa coherente | Alto | Alta |
| Incluir Partial Harnessing como **contender** en benchmark (modo "spec-only-then-release") | Medio | Alto | Alto | Alta |
| Reportar nuestros outcomes en términos de stage-wise recoverability vs. final success | Alto | Medio | Medio | Media |

---

## Decisiones recomendadas

### Harness (acciones priorizadas)

1. **HOY — Auditoría ψ**: revisar cada `agents/*.md` y clasificar reglas en **evidence-anchored** vs. **instruction-compliance**. Si predominan las segundas en un agente que se ve "alucinar", reducir λ (acortar el prompt) o reescribir reglas para anclar en evidencia. Coste 1h, riesgo evitado alto.

2. **Pre-benchmark — Modo Partial Harness**: añadir un quinto modo de misión donde solo se ejecutan SPEC + primer PLAN/IMPLEMENT, y el resto se delega al agente sin más estructura. **Es un experimento barato** sobre la arquitectura existente y prueba directamente la tesis P3.

3. **Mid-term — Capability-aware S/M/L**: parametrizar `TASK_PIPELINES` para que la elección S vs. M vs. L dependa también del modelo activo (Sonnet vs. Haiku). Junta P1 + paper 05 (capability-dependence).

4. **Investigar — Retention gap aproximado**: medir, sobre tareas REJECTED, cuál phase introdujo la trayectoria no-recuperable. Ya tenemos `audit.md`; añadir campo `recoverability_lost_at_stage`.

### Paper

5. **Cita central** en sección "Theoretical framing". Es el paper teórico de Mayo 2026 que **formaliza** lo que paper 03 (AI Harness Eng) ataca empíricamente y paper 07 (Vesper) demuestra ad-hoc. Trinity teórica perfecta:
   - Paper 03 → componentes del harness (qué tiene).
   - Paper 08 → cómo se compone matemáticamente (κ, λ, ψ).
   - Paper 07 → evidencia empírica que la composición importa.

6. **Adoptar la división de roles outer/inner**: nuestros agentes son `outer` (researcher, planner, structurer, reviewer) y `inner` (implementer, specifier en cierto modo). Lo encaja limpio en κ vs. λ,ψ.

7. **Modo Partial Harness como contender** en el benchmark — directamente contrasta nuestro full harness contra "spec-only" para validar P3 en SE tasks.

8. **NO adoptar todo el formalismo** (recoverability tubes, log-odds gaps). Es elegante pero exige notación pesada. Citarlo, no reproducirlo.

---

## Veredicto franco

Este es **el paper teórico más importante de la pila** para nuestro trabajo. Razones:

1. Da **fundamento matemático** a la idea central del paper de NEC (paper 07): el harness no es "siempre más es mejor". Pasamos de "anécdota empírica" a "consecuencia formal".
2. Predice un fenómeno (**Partial Harnessing**) que **ya estamos haciendo a medias** sin saberlo, y nos da el lenguaje para describirlo.
3. Identifica un riesgo arquitectónico real (P2: guidance que no se ancla en evidencia amplifica alucinación) que **podemos auditar y mitigar mañana**.
4. Provee vocabulario aceptable por reviewers teóricos (κ, λ, ψ, retention gap) sin que tengamos que probar teoremas — solo citarlos.

**Acción concreta inmediata** (priorizada):

1. **Auditoría ψ** (1h): clasificar reglas en `agents/*.md` evidence vs. compliance.
2. **Definir modo `MISSION_PIPELINES["partial"]`** = ["SPEC"] o ["SPEC","PLAN"] solamente; tarea inicial scaffold, resto al agente.
3. **Añadir contender "partial-harness"** al benchmark — predicción del paper testeable directamente en SE tasks.
4. **Citar como anchor teórico** del framework en la sección 2 del paper. Vocabulario (κ, λ, ψ) en glosario.

**Riesgo a evitar**: caer en la trampa formalista. El paper tiene 35 páginas con apéndices densos. Nuestro paper debe **citar las conclusiones, no reproducir las pruebas**. Hay belleza matemática pero ROI marginal en transcribirla.

---

## Síntesis con papers previos

- **Completa paper 03 (AI Harness Engineering)**: 03 enumera componentes (qué); 08 formaliza composición (cómo). Juntos = framework completo.
- **Explica empíricamente paper 07 (Vesper)**: Vesper observa "más coding-agent = mejor", que es un caso particular de P1 (más Mt → más reachable set → mejor scaling).
- **Refuerza paper 05 (Continual Harness)**: la capability-dependence de Gemini-Pro vs. Flash es **predicción directa de P1** (granularidad correcta depende de la capacidad).
- **Tensiona con paper 02 (Agent Hospital)**: simulacro vs. real cae bajo P2 — si el experience base premia "patrones que parecieron correctos en pacientes simulados" pero no se anclan en evidencia clínica real, retention gap negativo → alucinación clínica.
- **Diferenciado de paper 06 (DSPy)**: DSPy optimiza λ y ψ (prompts), no κ (estructura). Paper 08 muestra que κ es **igual o más importante**.
