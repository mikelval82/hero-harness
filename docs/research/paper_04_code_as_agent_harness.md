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

## 3. Mapeo a nuestro harness

| Categoría del paper | Nuestro estado |
|---------------------|----------------|
| Model-internal capabilities | Sonnet 4.x congelado, no tocamos |
| System-provided harness infrastructure | Sí: `PHASE_REGISTRY`, agentes, tools por fase, HITL, workspace efímero, layered context |
| **Agent-initiated code artifacts** | ❌ Mínimo. Nuestro implementer escribe código y tests, pero **no fabrica tools/scripts temporales** para verificar sub-tareas. Tampoco escribe skills reusables que persistan. |
| Code for reasoning | ⚠️ Parcial — el implementer ejecuta tests pero no usa programas como herramienta de razonamiento intermedio (PAL/PoT) |
| Code for acting | ✅ Edit/test/run cubierto |
| Code for environment | ⚠️ `build_code_graph` representa estado parcial. No tenemos modelo de tests fallidos como entorno explícito. |
| Planning | ✅ Specifier→Planner→Implementer es descomposición lineal con grounding estructural |
| Memory | ⚠️ Hot/cold per-mission. Sin memoria cross-misión (ya identificado en papers 02 y 03). |
| Tool use | ✅ Configurable por fase. No tenemos tool search/creation dinámica. |
| Feedback-driven control | ✅ Reviewer→reimplement loop |
| Multi-agent scaling | ⚠️ Tenemos roles (specifier/planner/implementer/reviewer) pero sequenced, no concurrentes. Es "streamlined collaboration" en su taxonomía, no "centralized" ni "distributed". |
| Harness como objeto de optimización | ❌ Nuestro harness es **estático**. No se auto-modifica ni se optimiza. |

---

## 4. Aplicabilidad — qué tomar del survey

### 4.1 Para el **harness** (implementación)

| Idea | Coste | Beneficio | Impacto | Novedad |
|------|-------|-----------|---------|---------|
| **Agent-initiated code artifacts:** permitir al implementer escribir scripts/tests temporales que ejecuta para verificar hipótesis | Medio. Requiere tool específico + política de cleanup | Medio-Alto. Combate "patching aleatorio" con verificación local | Alto en bugs sutiles | Media |
| **Code-as-reasoning (PAL/PoT style)** en specifier/planner para cálculos no triviales | Bajo | Bajo en nuestro dominio (code-gen, no math) | Bajo | Baja |
| **Multi-agent concurrente** (paralelizar specifier de subtareas) | Alto. Cambia el modelo de ejecución | Bajo a corto plazo | Bajo | Media |
| **Harness self-modification** (Live-SWE-agent style) | Muy alto. Estabilidad/rollback no resueltos en el paper | Incierto | Medio si funciona | Alta (competitiva con AutoHarness etc.) |
| **Externalizar convenciones de harness como specs editables** (Natural-Language Agent Harnesses) | Bajo — **ya lo hacemos** con `agents/*.md`, `CHECKPOINTS.md`, `CONTEXT.md` | Alto — nos da etiqueta de prior art | Alto a nivel narrativo | Baja en implementación, alta en framing |

### 4.2 Para el **paper / benchmark**

El valor principal del survey para nosotros es **referencial**, no metodológico.

| Uso | Valor |
|-----|-------|
| **Citar como source-of-truth de related work** | Muy alto. ~400 papers organizados; ahorra meses de literature review. |
| **Vocabulario tripartita** (model-internal / harness infra / agent-initiated code) | Alto. Encaja con nuestra narrativa: nuestro contender C3 maximiza harness infrastructure y deja agent-initiated code en mínimos; C1 Raw es sólo model-internal. |
| **Open problems documentados con métricas** | Muy alto. Nos da munición para justificar el paper ("failure attribution está al 14-53%; nosotros proponemos protocolo que mejora esto"). |
| **El thread "harness como objeto de optimización"** | Crítico. Identifica nuestros **competidores directos**: AutoHarness, Meta-Harness, AHE, NL Agent Harnesses, Live-SWE-agent. Hay que leerlos antes de publicar. |
| **"Harness as distillation surface"** | Alto. Argumento extra: los datos que produzca un buen harness valen oro para entrenar la siguiente generación de modelos. Eso refuerza el valor de invertir en harness engineering aunque los modelos mejoren. |
| **Como SOTA competidor** | No aplica. Es survey, no método. |

---

## 5. Análisis Riesgo · Beneficio · Impacto · Novedad

### 5.1 Como aporte directo al harness

Modesto. El survey cubre tanto terreno que casi todo lo que dice "se podría hacer" ya está en otros papers individuales más densos. **Tres ideas concretas vale la pena anotar:**

1. **Agent-initiated code artifacts** — dar al implementer (o introducir una fase nueva tipo "scratch") la capacidad de escribir scripts/probes que ejecuta para verificar hipótesis. **Coste medio, beneficio medio-alto en bug-fix.**
2. **Re-etiquetar nuestros `agents/*.md` como "Natural-Language Agent Harness"** — coste cero, alto valor narrativo.
3. **Leer los 5 papers del thread "harness as optimization object"** antes de seguir — son competencia directa, no derivar el plan sin verlos.

### 5.2 Como aporte al paper / benchmark

**Muy alto** como infraestructura referencial. Nos ahorra el grueso de la literature review y nos da open problems con métricas para justificar el aporte. La pregunta concreta es: **¿hay overlap peligroso con AutoHarness / Meta-Harness / AHE / Live-SWE-agent?** No podemos contestarla sin leerlos individualmente.

### 5.3 Riesgos

- **Riesgo de "todo ya está hecho":** el survey hace parecer que el espacio está saturado. En realidad cada pieza está aislada y nadie ha hecho el **estudio poblacional bajo H0–H3** (que sí está señalado como gap por Zhong & Zhu 2026 = paper 03). Nuestro nicho aguanta.
- **Riesgo de competencia con harness-as-optimization-object:** si AutoHarness o Meta-Harness ya muestran resultados empíricos comparables, nuestro paper queda en segunda fila. Hay que verificar.
- **Riesgo de quedarse derivativos:** este survey + paper 03 + paper 01 ya cubren mucho del marco. Para no parecer reseña, tenemos que **medir cosas nuevas** (estudio poblacional, jerarquía mission/task/burst, HITL fast-path).

---

## 6. Decisiones recomendadas

### Para el harness

1. **No** intentar auto-modificación del harness (Live-SWE-agent style). Demasiado coste, estabilidad no resuelta.
2. **Considerar** una fase opcional "scratch" donde el implementer puede generar scripts de verificación local antes de commit. Pequeña extensión natural del IMPLEMENT_BURSTS.
3. **Renombrar** o documentar nuestros `agents/*.md` como "natural-language agent harness specs". Bajo coste, da prior art.

### Para el paper

1. **Usar el survey como columna vertebral de la related work** — citarlo extensamente y construir nuestra sección de fundamentos sobre su taxonomía.
2. **Adoptar la distinción tripartita** (model-internal / harness infra / agent-initiated code) para describir qué hacen C1, C2, C3.
3. **Citar las cifras de open problems** (14-53% failure attribution, 16.9% LingmaAgent autonomy, organicity gap) para justificar el aporte empírico.
4. **Leer urgentemente** los siguientes papers antes de finalizar el research_plan:
   - AutoHarness
   - Meta-Harness
   - Agentic Harness Engineering (AHE)
   - Live-SWE-agent
   - Natural-Language Agent Harnesses
   
   Estos 5 son competencia directa; el research plan no debe cerrarse sin haberlos evaluado.

---

## 7. Veredicto franco

- **Como survey:** masivo, bien organizado, cita exhaustivamente. Útil como mapa.
- **Como contribución conceptual:** la distinción **agent-initiated code artifacts** vs. **system-provided infrastructure** es la idea propia del paper y es buena. El resto es síntesis.
- **Para nosotros:** **alto valor referencial, bajo valor metodológico.** No cambia el plan; sí cambia la literatura que tenemos que conocer.
- **Alerta principal:** el thread "harness as optimization object" tiene ~5 papers activos y nadie los ha leído todavía aquí. Si alguno de ellos hace estudio empírico sobre múltiples tareas con ablation, nuestro nicho se reduce. **Verificar antes de seguir invirtiendo en el plan actual.**

**Acción concreta sugerida:** mantener este paper como referencia maestra de la related work; priorizar lectura de **AutoHarness** y **Meta-Harness** en próximas iteraciones para descartar overlap.
