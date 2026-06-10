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

## 3. Qué adoptamos en HERO y cómo está implementado

HERO toma la **versión segura** de Continual Harness: un refiner que mejora el harness *entre* misiones con aprobación humana, en vez de auto-modificación online.

### Refiner post-misión (la idea fuerte del paper, adaptada)
- **Del paper:** un Refiner en outer loop que observa trazas y edita el harness (prompts, sub-agentes, skills, memoria).
- **En HERO:** `src/harness/refiner.py` lee `_telemetry.jsonl`, los `audit.md` y los fallos de la case base, detecta firmas de fallo recurrentes (`failure_type@stage` con recurrencia ≥ `REFINER_MIN_RECURRENCE = 2`) y **escribe una propuesta** (`refiner-proposal.md`) con evidencia y acciones. No aplica cambios: requiere aprobación humana (contrato en `docs/design/refiner_post_mission.md`, skill `commands/refine-harness.md`).

### Failure-signature detection sobre trazas
- **Del paper:** detectar loops, fallos de tool-call y objetivos estancados desde las trazas.
- **En HERO:** `_signals_from_telemetry()` en `src/harness/refiner.py` extrae señales de fallo de la telemetría (`src/harness/telemetry.py`).

### Modelo 4-componente (p, G, K, M) como artefactos editables
- **Del paper:** el estado del harness se descompone en system prompt $p$, sub-agentes $G$, skills $K$ y memoria $M$.
- **En HERO:** $p$ → `prompts/`; $G$ → `agents/*.md`; $K$ → `commands/`; $M$ → pizarra `context-hot/cold` + memoria persistente (`src/harness/project_memory.py`, `case_base.py`, `skill_library.py`). Son **editables entre misiones** (harness estático tipo "Hexpert"), y el refiner propone esas ediciones.

### Reset-free dentro de la misión
- **Del paper:** operación sin resets.
- **En HERO:** cada misión es atómica con workspace efímero nuevo; dentro de la misión, la ejecución es reset-free de facto (`src/mission/runner.py`).

## 4. No adoptado (y por qué)

- **Refiner mid-misión / auto-modificación online:** no se edita el harness en vivo. Nuestras misiones son cortas (minutos/horas, no días de Pokémon) y el propio paper muestra que la auto-modificación online es *capability-dependent* y frágil.
- **Meta-tools en runtime (`define_agent`, `run_code`, `edit_skill`):** el agente no puede crear sub-agentes ni reescribir su prompt durante la misión. Coste arquitectural alto (permisos, rollback, estabilidad) y beneficio bajo en nuestro régimen.
- **Co-learning modelo + harness:** fuera de scope; el modelo es frozen.
