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

## Qué adoptamos en HERO y cómo está implementado

Este paper formaliza la composición del harness como `(κ, λ, ψ)` (granularidad, fuerza y regla de guidance). HERO materializa varias de sus piezas.

### Partial harnessing como modos de misión (κ variable)
- **Del paper:** la estructura óptima no es "siempre más"; conviene un harness parcial (scaffold inicial + agente libre después).
- **En HERO:** los modos de misión **son** puntos en el espacio de granularidad: `--mode` admite `full`, `focused`, `spec`, `spec-plan`, `explore`, `hotfix` (`src/cli.py`), cada uno con su pipeline en `MISSION_PIPELINES` (`src/core/context.py`). `is_partial_harness_mode()` (`src/mission/task_executor.py`) distingue los modos parciales.

### ψ evidence-anchored vs instruction-compliance (riesgo P2)
- **Del paper:** un guidance que premia "seguir la instrucción" sin anclar en evidencia amplifica la alucinación.
- **En HERO:** el `reviewer` separa explícitamente ambos planos en `### Evidence Anchoring` (`status_claims_checked`, `unsupported_claims`, `evidence_quality`, `instruction_compliance_risk`), validado por gate (`src/core/gate.py`). El implementer debe aportar evidencia en `## Self-Verification`.

### Recoverability y atribución de etapa
- **Del paper:** *recoverability tubes*: un prefijo puede volverse no-recuperable en una etapa concreta.
- **En HERO:** el `audit.md` incluye `recoverability_lost_at_stage` y `failure_type` en la taxonomía de fallo del reviewer (`src/core/gate.py`); el HITL actúa como mecanismo de recovery (`src/mission/hitl.py`).

### Granularidad por complejidad + routing por fase (λ implícita)
- **Del paper:** κ (granularidad) y λ (fuerza del guidance) modulan el resultado.
- **En HERO:** la granularidad del pipeline depende de la complejidad de la tarea, y el modelo se enruta por fase (CHEAP/DEFAULT/DEEP en `src/core/model_policy.py`).

## No adoptado (y por qué)

- **Granularidad *capability-aware* (elegir S/M/L según el modelo, no la tarea):** el routing es por fase, pero el tamaño del pipeline se decide por complejidad de tarea, no por capacidad del modelo activo.
- **Marginal stopping rule en HITL:** no se detecta automáticamente cuándo añadir más checkpoints empeora el resultado.
- **Métrica formal de *retention gap* (Γ) y todo el aparato de *recoverability tubes* / log-odds:** se cita el resultado pero no se reproduce la notación pesada; ROI marginal frente a su coste.

---

## Síntesis con papers previos

- **Completa paper 03 (AI Harness Engineering)**: 03 enumera componentes (qué); 08 formaliza composición (cómo). Juntos = framework completo.
- **Explica empíricamente paper 07 (Vesper)**: Vesper observa "más coding-agent = mejor", que es un caso particular de P1 (más Mt → más reachable set → mejor scaling).
- **Refuerza paper 05 (Continual Harness)**: la capability-dependence de Gemini-Pro vs. Flash es **predicción directa de P1** (granularidad correcta depende de la capacidad).
- **Tensiona con paper 02 (Agent Hospital)**: simulacro vs. real cae bajo P2 — si el experience base premia "patrones que parecieron correctos en pacientes simulados" pero no se anclan en evidencia clínica real, retention gap negativo → alucinación clínica.
- **Diferenciado de paper 06 (DSPy)**: DSPy optimiza λ y ψ (prompts), no κ (estructura). Paper 08 muestra que κ es **igual o más importante**.
