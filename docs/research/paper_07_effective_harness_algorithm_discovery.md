# Paper 07 — Effective Harness Engineering for Algorithm Discovery with Coding Agents

- **Autores**: Yoichi Ishibashi, Taro Yano, Masafumi Oyamada (NEC Corporation)
- **ArXiv**: 2605.15221v1 (preprint, Mayo 2026)
- **Tipo**: Empírico aplicado / sistema (Vesper) + ablation studies
- **Archivo**: `papers/effective harness engineering for algorithm discovery with coding agents.pdf`

---

## 1. Tesis en una frase

En descubrimiento de algoritmos vía evolución LLM, **el diseño del harness pesa tanto o más que el modelo**: con el mismo modelo y mismo budget de tokens, un harness que invierte más tokens por iteración (coding agent autónomo) **bate al harness que genera muchos candidatos baratos** (single-shot API call estilo AlphaEvolve/OpenEvolve).

---

## 2. Piezas operativas clave

### Vesper — 4 mejoras de harness sobre el pipeline AlphaEvolve/OpenEvolve

| Componente | Cambio | Equivalente nuestro |
|---|---|---|
| **Coding Agent Integration** (§4.2) | Sustituir single-shot API call por agente autónomo (Codex CLI) con multi-step reasoning, repo read, test execution, debugging dentro de **una iteración** | Nuestro `implementer` + bursts |
| **Evaluation Hack Detection** (§4.3) | Agente secundario revisa cada candidato y rechaza los que explotan el evaluador | Análogo a `reviewer` aplicado a output |
| **DB Observation** (§4.4) | Pasa **path de SQLite** al agente; el agente lanza **SQL queries arbitrarias** para consultar trials previos (lineage, scores, ideas, diffs) | Análogo a `context-cold.md` + `code_graph.json` pero **agent-pull** vs nuestro **harness-push** |
| **Git Worktree Isolation** (§4.5) | Cada agente recibe un Git **worktree** (no clone) para aislamiento sin coste de disco | Nuestro `$CLAUDE_HARNESS` workspace efímero por misión |

### Pipeline Vesper (loop evolutivo)

1. **Select parent** branch del Program DB.
2. **Setup environment**: crear worktree.
3. **Improve programs**: coding agent autónomo (con DB observation).
4. **Evaluate**: scorer corre el candidato.
5. **Detect hacks**: agente secundario filtra.
6. **Update Program DB**: persistir branch + score + ideas estructuradas.

Hasta agotar token budget.

---

## 3. Hallazgos empíricos (Circle Packing n=26, 40M tokens)

| Configuración | Best score | #Algo | Tok/Algo |
|---|---|---|---|
| **Vesper** gpt-5.2-codex (hack ON, DB ON) | **2.63110** | 568 | 70.5K |
| **Vesper** gpt-5.2-codex (hack ON, DB OFF) | **2.63599** | 338 | 118.8K |
| Vesper gpt-5.1-codex-mini (hack ON) | 2.62721 | 101 | 400K |
| OpenEvolve gpt-5.2 | 2.41852 | 1,671 | 23.9K |
| OpenEvolve gpt-5.2-codex | 2.54142 | 1,510 | 26.5K |
| AlphaEvolve (Gemini, ref) | 2.6358 | — | — |
| Human best | 2.6340 | — | — |

**Finding 1 — Coding agent > stateless API**: Vesper con codex-mini supera a OpenEvolve con gpt-5.2 (modelo más grande). Harness > modelo.

**Finding 2 — Quality > Quantity** (la finding central): bajo budget fijo, **escalar reasoning por iteración** (89K tok/algo, 452 candidatos) bate a escalar generaciones (24K tok/algo, 1671 candidatos). Vesper supera el final score de OpenEvolve **a los 5M tokens** (12.5% del budget). Figura 3 muestra correlación monótona Tok/Algo ↔ Best score.

**Finding 3 — Modelos más capaces hackean más**: gpt-5.2-codex genera **8.2% de hacks**; codex-mini genera **0%**. Hack detection mejora con modelo grande, **empeora con modelo pequeño** (overhead sin beneficio). La necesidad de hack detection escala con capacidad.

**Finding 4 — DB Observation no ayuda (sorpresa)**: con DB ON el agente consume tokens en queries y baja el número de iteraciones; no hay beneficio neto en 2 runs. **El acceso a historia comprime peor que generar más candidatos** en este task. Caveat: 2 runs, sample minúsculo.

---

## 4. Qué adoptamos en HERO y cómo está implementado

### Evaluation hack detection
- **De Vesper:** el harness debe detectar cuándo el agente *gamea* el criterio en vez de resolver el problema; este riesgo crece con la capacidad del modelo.
- **En HERO:** el `reviewer` tiene una sección obligatoria `### Evaluation Hacking Check` (con `hardcoding_outputs`, `special_casing_tests`, `superficial_acceptance`) validada por gate (`src/core/gate.py`), y el refiner clasifica `evaluation_hacking` como tipo de fallo recurrente (`src/harness/refiner.py`).

### Quality > Quantity: bursts largos antes que muchos retries baratos
- **De Vesper:** invertir más tokens por iteración bate a iterar más veces de forma barata.
- **En HERO:** la implementación se ejecuta en bursts deliberados (`run_implement_bursts` en `src/mission/burst_runner.py`) con re-inyección de spec, en vez de muchos retries cortos sin contexto.

### Token budget y coste como métrica primaria
- **De Vesper:** medir bajo presupuesto de tokens, no por número de iteraciones.
- **En HERO:** la telemetría registra coste por fase y misión (`estimate_cost_usd`, `MODEL_PRICING_USD_PER_MTOK` en `src/core/model_policy.py`; `write_phase_event` en `src/harness/telemetry.py`), y el routing por fase (CHEAP/DEFAULT/DEEP) optimiza el gasto.

### Program DB con lineage (parcial)
- **De Vesper:** persistir el linaje de soluciones e ideas.
- **En HERO:** la case base (`src/harness/case_base.py`) persiste misiones aprobadas con su resumen (`mission-cases.jsonl`); no guarda un árbol de linaje evolutivo, pero sí trazabilidad cross-misión.

## 5. No adoptado (y por qué)

- **DB observation / agent-pull (acceso SQL del agente al contexto):** HERO usa contexto *harness-push* (compactación automática hot→cold). El propio Vesper reporta beneficio nulo de invertir a pull; no merece el cambio arquitectónico.
- **Git worktree por agente en paralelo / mission swarm:** HERO ejecuta una misión single-threaded; no hay exploración paralela con múltiples agentes. Aplicable solo si se añadiera búsqueda paralela.
- **Output estructurado `{branch, overview, score, diff, ideas}` por iteración:** parte de su intención se cubre con `status.md` + `## Self-Verification` + `### Gradient Findings`, pero no con ese esquema evolutivo exacto.
