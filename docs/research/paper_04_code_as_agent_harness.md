# Paper 04 — Code as Agent Harness: Toward Executable, Verifiable, and Stateful Agent Systems

**Autores:** Xuying Ning, Katherine Tieu, Dongqi Fu et al. (UIUC, Meta, Stanford). ~50 autores.
**arXiv:** 2605.18747v1, mayo 2026
**Tipo:** **Survey** (102 páginas, taxonomía + ~400 citas)
**Fichero:** `papers/code as agent harness.pdf`

---

## 1. Tesis del paper en una frase

Reframe: el código no es sólo lo que un agente **produce**; es el **medio operativo** (executable, inspectable, stateful) a través del cual razona, actúa, modela el entorno y verifica el progreso. El paper unifica la literatura bajo "code as agent harness" y la organiza en tres capas: **interface**, **mechanisms**, **scaling to multi-agent**. Es una **survey**, no contribuye método nuevo.

---

## 2. Lo verdaderamente útil del paper

Como es survey, lo que importa no es el contenido propio sino: (a) el **vocabulario formal** que introduce, (b) la **taxonomía** que da estructura a la related work, y (c) el **mapa exhaustivo de papers citables** con problemas abiertos identificados.

### 2.1 La distinción tripartita (esto es lo más valioso conceptualmente)

| Elemento | Qué es | Quién lo posee |
|----------|--------|----------------|
| **Model-internal capabilities** | Razonamiento, percepción, planning, simulación, evaluación del LLM | El modelo |
| **System-provided harness infrastructure** | Tools, APIs, sandboxes, memoria, validators, permission boundaries, telemetry, workflows predefinidos | El harness (estático) |
| **Agent-initiated code artifacts** | Tests, tools temporales, programas DSL, workflows ejecutables, skills reusables, program states intermedios — creados por el agente en runtime | El agente (dinámico) |

La tercera categoría es la que el paper considera **subexplorada**. La mayoría de literatura habla del modelo o del harness estático, pero no del código que el agente fabrica para sí mismo durante la tarea.

### 2.2 Las tres capas

- **§2 Harness Interface:** code for reasoning (programas externalizan computación), code for acting (programas como políticas/tools), code for environment (repos, traces, simuladores, tests como representación de estado).
- **§3 Harness Mechanisms:** planning (descomposición/estructural/trajectory search), memory (working state, RAG, experiencia), tool use, control & optimization (static analysis, runtime errors, tests, human feedback).
- **§4 Scaling the Harness:** multi-agent con roles (manager, planner, coder, reviewer, tester), modos (colaboración, debate, red-teaming), topologías (centralizado/distribuido/streaming).

### 2.3 Hilo emergente CRÍTICO: el harness como objeto de optimización

El paper destaca un sub-thread de 2024-2026 donde el propio harness es un artefacto **aprendible/optimizable**:

- **AutoHarness** — sintetiza código del harness desde feedback del entorno.
- **Meta-Harness** — formaliza optimización conjunta modelo–harness.
- **Agentic Harness Engineering (AHE)** — evoluciona harness por loop de observabilidad.
- **Natural-Language Agent Harnesses** — externaliza roles, contratos, adapters, convenciones de estado en specs editables (**esto es literalmente lo que son nuestros `agents/*.md`**).
- **Live-SWE-agent** — edita su propio scaffolding en runtime.

Implicación: ya hay competencia directa en "harness como first-class research object".

### 2.4 Open problems con métricas concretas

- **Failure attribution en multi-agent:** mejores resultados step-level **14-53%** de accuracy (Who&When, AgenTracer, AgentDebug). El paper la identifica explícitamente como "lack of structured traces for principled debugging".
- **Verification beyond unit tests:** oracle-adequacy crisis (PatchDiff, SWE-Bench++); gap correctness vs. security (Aardvark, Codex Security); **organicity gap** — parches funcionalmente correctos que maintainers rechazan.
- **Solution leakage en SWE-bench:** estudios muestran que parte de los "resueltos" llevan la pista en el issue text.
- **LingmaAgent (Alibaba prod):** 16.9% issues 100% autonomous, 43.3% con intervención manual. Dato bueno para contextualizar tasas reales.
- **Safety governance:** Aethelgard capability governor, Microsoft Agent Governance Toolkit como primeros pasos hacia least-privilege.
- **Stability/rollback** en harnesses auto-modificables — abierto.
- **Multi-agent state synchronization** sobre live repos — SyncMind.
- **Trust calibration en pair programming UX** — when to interrupt/checkpoint/delegate/defer.

### 2.5 "Harness as distillation surface"

Observación de 2026: las trazas del harness en producción se están convirtiendo en dataset de entrenamiento para la siguiente generación de modelos.

- **Cursor Composer:** RL online continuo sobre trazas reales de uso.
- **OpenAI codex-1 / GPT-5-Codex / GPT-5.1-Codex-Max:** entrenados explícitamente sobre interacciones largas que reflejan el loop del Codex harness.
- **Anthropic Claude Code:** dogfooding interno documentado en whitepaper "teams using Claude Code".

Implicación: la frontera "modelo vs. harness" se está volviendo una **superficie aprendible**.

---

## 3. Qué adoptamos en HERO y cómo está implementado

De la taxonomía del survey, HERO se sitúa claramente en el cuadrante **system-provided harness infrastructure**: maximiza la infraestructura del harness y deja al mínimo el *agent-initiated code*.

### Harness infrastructure (model-external)
- **Del survey:** la capacidad emerge del sistema `model × harness × environment`; la infraestructura del harness es donde se invierte.
- **En HERO:** pipeline declarativo de fases con agentes, herramientas por fase, gates, HITL, workspace efímero y pizarra por capas (`PHASE_REGISTRY` en `src/core/context.py`, `agents/*.md`, `src/mission/`).

### Planning como descomposición lineal con grounding estructural
- **Del survey:** planificación explícita antes de actuar.
- **En HERO:** `specifier → planner → implementer → reviewer` (`agents/*.md`), con grounding del grafo de código (`src/analysis/`).

### Code for acting + feedback-driven control
- **Del survey:** el código como medio de actuar y el control guiado por feedback de ejecución.
- **En HERO:** el implementer edita/ejecuta tests (`IMPL_TOOLS` en `src/core/context.py`) y el loop reviewer → reimplement reacciona al `audit.md` (`src/mission/hitl.py`, `src/mission/burst_runner.py`).

### Natural-Language Agent Harness specs
- **Del survey:** externalizar las convenciones del harness como specs editables en lenguaje natural.
- **En HERO:** exactamente eso — los roles viven en `agents/*.md`, los criterios en `CHECKPOINTS.md`, el vocabulario en `GLOSSARY.md` y las skills en `commands/`.

### Memory (ahora cross-misión)
- **Del survey:** memoria como componente del harness.
- **En HERO:** además de la pizarra `context-hot.md`/`context-cold.md` (per-misión), hay memoria persistente cross-misión: case base (`src/harness/case_base.py`) y project memory (`src/harness/project_memory.py`).

## 4. No adoptado (y por qué)

- **Agent-initiated code artifacts (scripts/probes temporales):** el implementer escribe código y tests, pero no fabrica herramientas/scripts efímeros para verificar sub-hipótesis. Requeriría un tool de "scratch" con política de limpieza.
- **Code-as-reasoning (PAL/PoT):** poco relevante en un dominio de code-gen (no de cálculo matemático).
- **Multi-agente concurrente:** los roles están secuenciados ("streamlined collaboration" en la taxonomía del survey), no ejecutados en paralelo.
- **Harness auto-modificable (Live-SWE-agent style):** el harness es estático; no se auto-optimiza. La estabilidad/rollback de la auto-modificación no es un problema resuelto.
