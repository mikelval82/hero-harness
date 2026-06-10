# Paper 05 — Continual Harness: Online Adaptation for Self-Improving Foundation Agents

**Autores:** Seth Karten, Joel Zhang et al. (Princeton, ARISE Foundation, Google DeepMind)
**arXiv:** 2605.09998v1, mayo 2026
**Tipo:** Paper aplicado con método nuevo + experimentos (Pokémon Red/Emerald, Gemini 3 variants)
**Fichero:** `papers/continual harness_online adaptation for self improving foundation agents.pdf`

---

## 1. Tesis del paper en una frase

Mientras los harnesses de coding (Claude Code, OpenHands) son **estáticos**, no existe equivalente para agentes embodied de largo horizonte. Proponen **Continual Harness**: un harness que se **auto-refina mid-episode** sin reset, vía un Refiner LLM que edita CRUD-style los 4 componentes del harness (prompt, sub-agentes, skills, memoria). Resultado: en Pokémon Red/Emerald con Gemini 3, recuperan la mayoría del gap entre baseline mínimo y harness experto hand-engineered, **partiendo de cero**.

Tres etapas: (1) human-in-the-loop (sus GPP runs, primera IA en completar varios Pokémon), (2) self-improving harness (automatiza al humano), (3) co-learning modelo+harness con PRM + soft SFT.

---

## 2. Las piezas operativas

### 2.1 Descomposición del harness en 4 componentes

| Componente | Símbolo | Contenido |
|------------|---------|-----------|
| System prompt | $p$ | Instrucciones y guía estratégica |
| Sub-agents | $G$ | Módulos especializados invocables (battle, puzzle, reflection) |
| Skills | $K$ | Rutinas reusables — heurísticas NL + programas ejecutables (pathfinders, wrappers de tools) |
| Memory | $M$ | Knowledge store persistente: facts, strategies, observaciones |

Y un set fijo de **meta-tools** (`define_agent`, `run_code`, `process_memory`, notepad edits, custom tool creation) que el modelo y el Refiner usan para editar $p, G, K, M$ in place.

### 2.2 Two-loop architecture

- **Inner loop:** el modelo $M$ envuelto por el harness $H_t$ produce $a_t$ desde $s_t$ y trayectoria.
- **Outer loop:** cada $F$ steps tras warm-up $W$, el Refiner lee la ventana reciente $\tau_{t-F:t}$, identifica *failure signatures* (loops de navegación, tool-call failures, objetivos estancados, exploración perdida) y emite ediciones por componente $\Delta = (\Delta_p, \Delta_G, \Delta_K, \Delta_M)$.
- **Reset-free:** el agente no resetea. $H_{t+1} = H_t \oplus \Delta$. Esto contrasta con GEPA y prompt-optimization que requieren reset completo entre updates.

### 2.3 Co-learning modelo + harness (la pieza más ambiciosa)

- Cada iteración corre $\pi_{\theta_k}$ dentro del harness vivo refinándose por $K=256$ steps.
- Un PRM pairwise puntúa cada transición.
- Ventanas de baja recompensa son **relabel** por un teacher frontier (Gemini-3.1-pro).
- Soft SFT con LoRA actualiza $\theta_{k+1}$.
- **Reset-free de verdad:** el emulator state al final de iter $k$ es el inicio de iter $k+1$, no hay reset al inicio del juego.

### 2.4 Resultados clave (Pokémon Red/Emerald, Gemini 3)

- Continual Harness, **partiendo de harness mínimo**, recupera mayoría del gap al expert harness hand-engineered.
- **Capability-dependent:** Pareto-dominant en Gemini 3 Pro, alta varianza en Flash, **por debajo del capability floor en Flash-Lite**. Es decir, modelos pequeños no pueden refinarse a sí mismos eficazmente.
- Co-learning loop produce progreso sostenido en milestones de Pokémon Red con Gemma-4 open-source.

---

## 3. Mapeo a nuestro harness

| Componente Continual Harness | Equivalente nuestro | Estado |
|------------------------------|---------------------|--------|
| $p$ system prompt | Templates en `prompts/` y mode pipelines | ✅ Estático. Nunca se reescribe en runtime. |
| $G$ sub-agents | `agents/*.md` (researcher, specifier, planner, implementer, reviewer, ...) | ✅ Estático. No se crean ni eliminan durante una misión. |
| $K$ skills | `commands/` (custom commands editables) | ✅ Estáticos. El humano los edita entre misiones. |
| $M$ memory | `context-hot.md` + `context-cold.md` + `code_graph.json` | ⚠️ Dinámico **dentro** de una misión, pero no editado por un Refiner LLM dedicado; sólo compactado heurísticamente. |
| Meta-tools (`define_agent`, `run_code`, ...) | — | ❌ No existen. El agente actual no puede crear sub-agentes, modificar skills, ni reescribir su propio system prompt. |
| Refiner outer loop cada $F$ steps | — | ❌ No tenemos refiner. El reviewer es el más parecido pero sólo aprueba/rechaza el output, no edita el harness. |
| Reset-free | ⚠️ Las misiones sí son atómicas y la siguiente arranca con workspace nuevo. Dentro de la misión sí es reset-free de facto. | Parcial |
| Co-learning modelo+harness | ❌ Modelo congelado (Sonnet) | N/A — fuera de scope |

**Posición:** somos un harness **estático tipo Hexpert** (en su terminología). Nuestro valor humano es justo el "human refiner" de GPP fase (1). Continual Harness automatizaría esa fase humana.

---

## 4. Aplicabilidad — qué tomar de este paper

### 4.1 Para el **harness** (implementación)

| Idea | Coste | Beneficio | Impacto | Novedad |
|------|-------|-----------|---------|---------|
| **Refiner post-misión** que lee `audit.md` + trazas y propone ediciones a `agents/*.md`, `commands/`, prompts | Medio. Loop async fuera del runner. Humano aprueba antes de aplicar | Alto a medio plazo. Convierte cada misión en oportunidad de mejora del harness | Alto en uso continuado | Alta — alinea con thread "harness as optimization object" sin riesgo de auto-modificación en vivo |
| **Refiner mid-misión** (cada N tareas o N bursts, no cada F steps) que edita prompts/skills | Alto. Estabilidad/rollback no triviales. Riesgo de degradar el harness en vivo | Bajo-Medio. Las misiones nuestras son cortas comparadas con Pokémon (horas vs días) | Bajo en nuestro régimen | Alta |
| **Meta-tools** (`define_agent`, `run_code`, `edit_skill`) expuestas al agente | Muy alto. Cambio arquitectural mayor; estabilidad, permisos, rollback | Bajo a corto. Alto a largo. | Bajo en nuestro régimen actual | Alta |
| **4-componente harness state** ($p, G, K, M$) como modelo explícito de qué se puede editar | Bajo (conceptual) | Medio. Da estructura clara para futuras extensiones | Medio | Baja |
| **Failure signatures** detectadas automáticamente sobre trazas (loops, tool-call failures, stalled objectives) | Bajo | Medio. Telemetría útil incluso sin Refiner | Medio | Baja |
| **Co-learning modelo+harness** | Fuera de scope (modelo frozen) | — | — | — |

### 4.2 Para el **paper / benchmark**

| Uso | Valor |
|-----|-------|
| **Citar como contraste de dominio** | Alto. Su dominio (embodied/Pokémon) es complementario al nuestro (code-gen). Refuerza la generalidad de "harness as object of optimization". |
| **Adoptar la descomposición 4-componente** ($p, G, K, M$) como vocabulario | Alto. Da formalismo claro y permite describir nuestros 3 contenders en función de qué partes están presentes/refinables. |
| **Punto de "capability-dependent gains"** | Alto. Su hallazgo de "Continual Harness funciona en Pro, falla en Flash-Lite" es directamente relevante a nuestra hipótesis: el beneficio del harness puede ser **no monotónico en capacidad del modelo**. Sugiere experimento opcional con un modelo más pequeño. |
| **Reset-free como propiedad de diseño** | Medio. Nuestra `mission` es reset (workspace efímero); dentro de una misión, somos reset-free. Vocabulario útil. |
| **Como competencia directa** | **No.** Dominio distinto, método ortogonal. Más bien complementario en una taxonomía de harnesses auto-mejorantes. |

---

## 5. Análisis Riesgo · Beneficio · Impacto · Novedad

### 5.1 Como aporte al harness

- **Idea fuerte:** Refiner **post-misión** (no mid-misión) que lee trazas + `audit.md` y propone ediciones a `agents/*.md`, prompts, `commands/`. **Humano aprueba**, no se aplica solo. Es la versión segura de Continual Harness para nuestro régimen.
  - Coste medio, beneficio alto a medio plazo, novedad alta en framing.
- **Idea débil para nosotros:** Refiner mid-misión y meta-tools. Coste alto, beneficio bajo dado que nuestras misiones son cortas. El paper mismo muestra que esto requiere capacidad del modelo grande (Pro funciona, Flash-Lite no) — y aún con modelos pequeños fracasa.
- **Failure signatures automáticas** sobre trazas: útil aunque no haya Refiner. Sólo telemetría.

### 5.2 Como aporte al paper

Buen contraste de dominio para mostrar que el harness importa también fuera de coding. La descomposición 4-componente es vocabulario aprovechable. Su finding de "capability-dependent gains" es **un detalle importante** que conviene replicar/citar: el beneficio del harness no es plano respecto a la capacidad del modelo, lo que tiene implicaciones para H1-H5 del research_plan.

### 5.3 Riesgos

- Si abrazamos demasiado el thread "self-improving harness", entramos en competencia con un thread saturado (paper 04 listó 5 papers en él). Nuestro nicho es el **harness estático bien diseñado**, no el auto-modificable.
- Confundir "Refiner entre misiones" con "harness self-modifying" — son cosas distintas. La primera es práctica de meta-learning offline, la segunda es self-modification online (riesgosa, capability-dependent).

---

## 6. Decisiones recomendadas

### Para el harness

1. **Considerar a futuro** un Refiner **post-misión** + **human approval** que sugiera ediciones a `agents/*.md`, prompts, `commands/`. Es una skill opcional, fuera del runner.
2. **No** introducir meta-tools en runtime para que el agente edite su harness mid-misión. Coste alto, beneficio bajo en nuestro régimen, riesgo de inestabilidad.
3. **Adoptar la nomenclatura 4-componente** ($p, G, K, M$) en la documentación del harness. Cero coste, claridad arquitectural.
4. **Implementar failure-signature detection** sobre trazas (loops de tool-calls, stalled status.md, repeated edits) como telemetría — incluso sin Refiner. Útil para HITL y debug.

### Para el paper

1. **Citar** como evidencia de que la frontera "harness vs. modelo" se está volviendo aprendible (alineado con "harness as distillation surface" de paper 04).
2. **Adoptar** el formalismo $p, G, K, M$ + meta-tools como marco para describir nuestros contenders en la sección de método.
3. **Considerar añadir** un mini-experimento secundario: correr nuestro benchmark con un modelo más pequeño (Sonnet 4 → Sonnet 3.5 o Haiku) para testar la hipótesis "capability-dependent harness gains". Bajo coste, alto valor empírico, alineado con su finding.
4. **Posicionarnos como complementarios:** ellos auto-refinan el harness para un dominio donde no hay harness experto; nosotros validamos que un harness estático bien diseñado domina a baselines en un dominio (code-gen) donde sí hay harness expertos.

---

## 7. Veredicto franco

- **Calidad del paper:** alto. Tiene método claro, experimentos serios, dos loops bien diferenciados, contribución empírica (primer AI en completar varios Pokémon) y resultados con caveats honestos (capability-dependent).
- **Relevancia para nosotros:** **media.** Dominio muy distinto. La idea del Refiner es importante pero su aplicación literal (mid-episode, meta-tools en runtime) no es para nosotros. La aplicación **adaptada** (Refiner post-misión con aprobación humana) sí merece exploración.
- **Lo más valioso:**
  - Formalismo 4-componente $(p, G, K, M)$ + meta-tools.
  - Finding empírico: harness gains son capability-dependent, no monotónicos.
  - El reset-free como propiedad de diseño con implicaciones prácticas.
- **Lo menos relevante:** co-learning modelo+harness (irrelevante porque trabajamos con LLM frozen propietario).

**Acción concreta sugerida:**
1. Adoptar nomenclatura $p, G, K, M$ en docs del harness.
2. Anotar **Refiner post-misión** como skill opcional a futuro.
3. Plantear como experimento opcional del benchmark: "harness benefit como función de model capability" usando 2 tamaños de modelo.
