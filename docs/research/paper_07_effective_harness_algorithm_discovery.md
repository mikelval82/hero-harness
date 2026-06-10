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

## 4. Mapeo a nuestro harness

| Concepto Vesper | Estado en nuestro harness | Gap |
|---|---|---|
| Coding agent integration | ✅ Es nuestra premisa de partida | — |
| Token budget vs candidate count | ❌ No explícito | Análogo: misión completa vs N retries |
| Hack detection | ⚠️ Implícito en `reviewer` pero NO clasifica evaluation-hacking | Falta detector específico de "cumple acceptance pero gamea criterio" |
| DB observation (SQL pull) | ❌ Nuestro contexto es **harness-push** (compactación auto), no **agent-pull** | Cambio arquitectónico interesante |
| Git worktree per agent | ⚠️ Tenemos workspace efímero, pero **no múltiples agentes en paralelo** | No aplicable hoy (single-mission), aplicable si añadimos exploración paralela |
| Program DB con lineage + ideas | ❌ No persistimos lineage entre tareas | Convergente con paper 02 (mission case base) |
| Quality vs Quantity finding | ❓ No hemos medido | **Test interesante**: ¿conviene 1 implementer largo o 3 bursts cortos? |

---

## 5. Análisis Aplicabilidad — Harness

| Idea Vesper | Coste integrar | Beneficio | Impacto | Novedad |
|---|---|---|---|---|
| **Evaluation hack detection** (reviewer-bis sobre artefacto) | Bajo (extender `reviewer.md`) | Medio | Alto si tarea es evaluable automáticamente; bajo en tareas con criterios subjetivos | Media (es reward hacking clásico) |
| **DB observation (agent SQL access)** sobre case base | Alto (SQLite + tool spec) | Incierto (paper dice "no benefit"); pero su task es evolutivo single-domain | Medio | Alta — invertir push→pull es decisión arquitectónica fuerte |
| **Worktree per parallel agent** | Medio | Solo aplica si añadimos búsqueda paralela (mission swarm) | Alto si vamos a multi-mission | Media (git feature estándar) |
| **Quality > Quantity principle** | Cero (es metodología) | Alto: justifica nuestros bursts largos vs OpenAI Codex single-shot | Alto en mensaje del paper | Media — empírico claro pero contexto-específico |
| **Structured output {branch, overview, score, diff, ideas}** por iteración | Bajo (formato en `status.md`) | Medio si vamos a persistir cross-mission | Medio | Baja |
| **Hack detection escala con capability** | Cero (es hallazgo) | Alto en interpretación: la verificación importa más con modelos mejores | Alto narrativamente | Alta — contraintuitivo |

## 5b. Análisis Aplicabilidad — Paper (research_plan)

| Uso | Coste | Beneficio | Impacto | Novedad |
|---|---|---|---|---|
| **Citar como evidencia empírica de "harness > model"** | Cero | Alto — paper directamente afirma la tesis central de nuestro paper | Alto | — (refuerzo) |
| **Citar Finding 2 (quality > quantity)** como soporte de bursts largos | Cero | Alto — justifica nuestro diseño vs harnesses single-shot | Alto | Convergente |
| **Citar Finding 3 (capability ↔ hacking) ** como ejemplo de "harness needs to evolve with model" | Cero | Medio | Medio | Cita curiosa |
| **Diferenciarnos**: Vesper = búsqueda evolutiva de algoritmos; nosotros = orquestación de misiones de desarrollo | Cero | Crítico para evitar overlap | Alto | — |
| **Añadir como contender**: NO. Distinto régimen (evolutionary loop vs HITL pipeline) | — | — | — | — |
| **Adoptar token-budget como métrica** en benchmark | Bajo | Alto — mucho más justo que "número de tareas" | Alto | Media (estándar emergente) |

---

## 6. Decisiones recomendadas

### Para el harness

1. **Adoptar token budget como restricción primaria en benchmark** (no número de misiones). Reportar `tokens_per_mission` y `cost_per_mission` siempre.
2. **Extender `reviewer.md`** con sección "evaluation hack detection": ¿el código pasa los acceptance criteria pero **gamea** el criterio? (e.g. hardcoding de outputs esperados, special-casing de inputs del test). Coste bajo, beneficio alto, alineado con R-CG1 del paper 03.
3. **NO migrar a agent-pull DB observation**. Nuestro layered context (push) funciona y Vesper mismo reporta beneficio nulo. Mantener compactación automática.
4. **Diseñar mini-experimento Quality vs Quantity** post-MVP: misma misión, mismo budget, comparar (a) 1 IMPLEMENT largo, (b) 3 IMPLEMENT_BURSTS, (c) 5 retries cortos. Predicción Vesper: (a) > (b) > (c). Verificarlo en nuestro régimen.
5. **Worktree per agent**: dejar como diseño futuro **si y solo si** introducimos exploración paralela (mission swarm). Hoy no aplica.

### Para el paper

1. **Citar como evidencia empírica directa** de "harness > model" en sección de motivación. Es el paper que mejor lo demuestra cuantitativamente.
2. **Citar Finding 2 (quality > quantity)** como soporte teórico del diseño de bursts largos vs harnesses single-shot tipo OpenAI Codex.
3. **Citar Finding 3 (capability ↔ hacking)** como argumento de "harness debe evolucionar con el modelo" — encaja con paper 05 (capability-dependent gains) y paper 03 (verification protocol).
4. **Diferenciarnos explícitamente**: Vesper = evolutionary search sobre code; nosotros = HITL pipeline para desarrollo de features. Régimen distinto pero hallazgos transferibles.
5. **NO incluir Vesper como contender en benchmark** — wrong régimen. Sí incluir su finding como hipótesis a verificar en nuestro setting.

---

## 7. Veredicto franco

Paper **muy bien construido** y **uno de los más alineados con nuestra tesis**. Es la evidencia empírica que nos faltaba: en un dominio totalmente distinto (búsqueda evolutiva de algoritmos), demuestran cuantitativamente que **harness > modelo** y que **invertir más tokens por iteración bate a iterar más veces baratas**. Ambas son tesis nuestras pero **no las hemos demostrado** todavía.

**Riesgo**: confundir su régimen con el nuestro. Vesper opera en un loop evolutivo cerrado con scorer automático; nosotros operamos en un pipeline lineal con HITL. Algunos hallazgos no transfieren (DB observation puede ayudar más en nuestro caso porque las misiones son heterogéneas; hack detection es menos relevante porque tenemos humano en el loop).

**Acción concreta sugerida**:
1. **Inmediata**: añadir Finding 1+2+3 como citas en `research_plan/research_plan.md` sección "evidencia empírica de harness > model".
2. **Corto plazo**: extender `reviewer.md` con check explícito de "evaluation hacking" (¿el código gamea el acceptance criteria?). Coste bajo, beneficio claro.
3. **Medio plazo**: diseñar mini-experimento Quality vs Quantity en nuestro benchmark — es testeable y nos da datos propios sobre la misma pregunta.
4. **NO hacer**: rewrite a agent-pull DB observation, ni añadir Vesper como contender en benchmark.

**Lo más importante que aporta este paper a nuestro trabajo**: nos da **munición empírica cuantitativa** (Figura 2: 5M tokens basta para superar a OpenEvolve final, 12.5% del budget) para defender la elección arquitectónica "agente autónomo con bursts largos" frente a la alternativa "muchos retries baratos". Es el paper que **podemos citar para justificar nuestra decisión de diseño más controvertida**.
