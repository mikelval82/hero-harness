# Paper 06 — DSPy: Compiling Declarative Language Model Calls into Self-Improving Pipelines

**Autores:** Omar Khattab, Arnav Singhvi et al. (Stanford, UC Berkeley, CMU, Amazon, IIT Bombay, Microsoft, Two Sigma)
**arXiv:** 2310.03714v1, octubre 2023 (paper original; DSPy ha evolucionado mucho desde entonces)
**Tipo:** Paper de **framework** + 2 case studies empíricos (GSM8K, HotPotQA)
**Fichero:** `papers/DSPY - compiling declarative language model calls into self-improving pipelines.pdf`

---

## 1. Tesis del paper en una frase

Los pipelines de LLM se construyen como "long strings of prompt templates" hand-crafted por trial-and-error. DSPy propone tratar los pipelines como **grafos de transformación de texto** con tres abstracciones: **signatures** (specs declarativas I/O), **modules** (transformaciones parametrizadas tipo PyTorch layer), y **teleprompters** (compiladores que optimizan los prompts/demonstraciones de cada módulo contra una métrica).

Es un framework para **compilar prompts**, no un harness en nuestro sentido.

---

## 2. Las tres abstracciones

### 2.1 Signatures

Declaración de función NL-typed: `question -> answer`, `english_document -> french_translation`. Define **qué** hace una transformación, no **cómo** se prompetea. DSPy expande nombres de campos en instrucciones para el LM.

```python
qa = dspy.Predict("question -> answer")
qa(question="Where is Guaraní spoken?")
```

### 2.2 Modules

Como capas de PyTorch. Encapsulan técnicas de prompting (`Predict`, `ChainOfThought`, `ReAct`, `MultiChainComparison`, `ProgramOfThought`) parametrizadas por **demonstraciones** que aprenden vía bootstrap.

### 2.3 Teleprompters (compilers)

Optimizadores. Input: programa DSPy + métrica + pocos ejemplos (opcionalmente etiquetados). Output: prompts/demonstraciones optimizadas. Estrategias: cross-validation, bayes-opt, RL, LM feedback. El compiler **simula el programa**, **bootstrap trazas** y **selecciona few-shot examples efectivos**.

### 2.4 Resultados originales (GPT-3.5 / Llama2-13b-chat / T5-770M)

- GSM8K: 33% → 82% (GPT-3.5), 9% → 47% (Llama2-13b-chat).
- HotPotQA: 32% → 46% (GPT-3.5), 22% → 41% (Llama2-13b-chat).
- Programas DSPy en modelos pequeños (T5-Large 770M, Llama2-13b-chat) competitivos con expert-prompted GPT-3.5.

---

## 3. Mapeo a nuestro harness

| DSPy | Nuestro harness | Estado |
|------|-----------------|--------|
| Signature | Cabeceras de prompts en `prompts/*.md` (input fields del template) | ⚠️ Implícitas, no formales. No hay tipado de IO. |
| Module | Nuestros **agentes** (`researcher`, `specifier`, `planner`, `implementer`, `reviewer`) | ⚠️ Funcionalmente similares pero hand-crafted, no parametrizados |
| Teleprompter / compiler | — | ❌ No tenemos. Prompts y agentes son hand-tuned. |
| Bootstrap de demonstraciones | — | ❌ No tenemos. No persistimos trazas exitosas como few-shot examples para futuras misiones (gap ya identificado en paper 02). |
| Métrica de optimización | — | ❌ Implícita (APPROVED del reviewer), no formalizada como score numérico para optimizar |
| Pipeline como grafo computacional | `PHASE_REGISTRY` + `MissionRunner` | ✅ Pero el grafo es fijo, no parametrizado |

**Posición:** somos un harness con la **estructura de un programa DSPy** (modules + pipeline) pero sin **compiler** (sin teleprompter). Equivalemos a un pipeline DSPy ejecutado en modo eager con prompts fijos.

---

## 4. ¿Podríamos integrar DSPy?

### 4.1 Lo que se traduciría bien

- **Reescribir cada agente** (`researcher`, `specifier`, etc.) como `dspy.Module` con signature explícita. Bajo coste técnico (rewrite de prompts a signatures + Module subclasses).
- **Definir una métrica compuesta**: `APPROVED rate` + `M-HIR` + `entropy delta` + `cost` (los outcomes del paper 03). DSPy puede optimizar contra cualquiera de ellas o combinaciones.
- **Bootstrap demonstrations**: cuando una misión llega a `autonomous_verified_success`, persistir el `(brief, spec, plan, audit)` como demonstración few-shot para futuras invocaciones del módulo correspondiente.
- **Teleprompter offline**: una vez tengamos N misiones reales, correr `BootstrapFewShot` o `MIPRO` para optimizar prompts de cada agente.

### 4.2 Lo que NO se traduce limpio

- **HITL fast-path**, **reimplement loop**, **mission/task/burst jerarquía**, **layered hot/cold context**: DSPy no tiene primitivas naturales para esto. Habría que codificarlas como `if/for` en Python alrededor de los módulos DSPy, pero el compiler no las optimiza.
- **Workspace efímero + artefactos en disco**: DSPy asume pipelines de in-memory string transformations. Tendríamos que serializar/deserializar entre módulos.
- **Reviewer como módulo recursivo** (audit → reimplement → re-audit): difícil de expresar con el compiler de DSPy, que asume DAG.
- **Métricas non-pass/fail** sobre código real: DSPy funciona mejor con métricas baratas y deterministas. Nuestras métricas reales (tests reales, reviewer LLM) son caras.

### 4.3 Coste real de migrar

- **Alto.** No es sólo reescribir prompts: es asumir el modelo mental de DSPy, gestionar versionado del compiler, lidiar con sus limitaciones de control flow, y aceptar dependencias.
- **Beneficio sólo si** corremos el harness sobre N misiones suficientes (≥30) y tenemos métricas baratas que el teleprompter pueda evaluar muchas veces. Hoy no.

---

## 5. Análisis Riesgo · Beneficio · Impacto · Novedad

### 5.1 Como aporte al harness

| Idea derivada | Coste | Beneficio | Impacto | Novedad |
|---------------|-------|-----------|---------|---------|
| **Migrar agentes a DSPy modules** | Alto | Medio-Alto si llegamos a corpus de misiones para compilar | Medio | Baja (DSPy ya existe) |
| **Adoptar signatures NL-typed** sin migrar a DSPy | Bajo. Es una práctica de documentación | Medio. Claridad estructural en prompts | Medio | Baja |
| **Bootstrap demonstrations cross-misión** (idea de teleprompter sin DSPy) | Medio. Es la "mission case base" del paper 02 + selección via métrica | Alto a medio plazo | Alto | Media — combina paper 02 (case base) + paper 06 (selección via teleprompter) |
| **Métrica formal compuesta** sobre outcomes (paper 03) para guiar optimización futura | Bajo (definición) + Alto (instrumentación) | Alto a largo plazo | Alto | Media |
| **Teleprompter offline** sobre N misiones para auto-optimizar prompts | Muy alto. Requiere N≥30 misiones, métricas evaluables, infra | Alto si funciona | Alto | Media — es DSPy aplicado a coding agents, no muy explorado todavía |

### 5.2 Como aporte al paper / benchmark

| Uso | Valor |
|-----|-------|
| **Citar como prior art** de "harness como programa parametrizable" | Alto. Es la cita obligada para "pipelines de LLM como código declarativo". |
| **Diferenciarnos** explícitamente | Crítico. DSPy optimiza **prompts**; nosotros optimizamos **orquestación, contexto, HITL**. Son ortogonales. |
| **Comparar con DSPy como contender** | Potencialmente. Podríamos añadir **C4 = DSPy pipeline** al benchmark. Aumenta el coste de implementación. **Decisión depende de presupuesto.** |
| **Adoptar terminología** signatures/modules/teleprompters | Medio. Útil pero arriesga confusión con DSPy literal. |
| **Como SOTA en coding agents** | No. DSPy se ha probado más en QA/math que en SWE-bench-like tasks. No es competidor empírico fuerte aquí. |

### 5.3 Riesgos

- **Tentación de migrar todo a DSPy.** Es muy atractivo "y si todo lo nuestro fuera DSPy modules y compiláramos". Realidad: rewrite enorme, no resuelve los problemas duros del harness (workspace, HITL, contexto), y nos hace dependientes de una librería en evolución rápida.
- **Confundir prompt optimization con harness optimization.** DSPy optimiza la primera. La segunda es lo nuestro. Mantener la distinción es clave para la narrativa.
- **DSPy ha cambiado mucho desde 2023.** Esta versión del paper es antigua. El framework actual tiene MIPROv2, COPRO, ensembling, etc. Si lo citamos, conviene citar también la versión reciente del repo y de papers DSPy posteriores.

---

## 6. Decisiones recomendadas

### Para el harness

1. **No migrar a DSPy.** El coste excede el beneficio en nuestro régimen actual.
2. **Adoptar la práctica de signatures explícitas** en los headers de `prompts/*.md` (input/output fields documentados). Cero coste, mejora claridad. **No usar el framework**, sólo la idea.
3. **Tomar prestada la idea de teleprompter para "mission case base"**: en lugar de simple retrieval por similitud (paper 02), seleccionar demonstrations vía bootstrap guiado por métrica. Esto es la **versión 2.0 de la mission case base**. Anotar para post-MVP.
4. **Formalizar métrica compuesta** sobre outcomes del paper 03 (`AVSR`, `M-HIR`, `cost`, `entropy_delta`). Útil incluso sin DSPy: define qué optimizar manualmente y qué medir en el benchmark.

### Para el paper

1. **Citar DSPy** como prior art en "pipelines LLM parametrizables y compilables".
2. **Diferenciarnos** explícitamente: DSPy = prompt optimization; nuestro paper = harness orchestration + workspace + HITL + layered context.
3. **No añadir DSPy como contender** salvo que el presupuesto permita 4 contenders sólidos. Mantener los 3 actuales (C1 Raw, C2 Loop tonto, C3 Harness) que ya cubren H0/H1/H3 del paper 03.
4. **Mencionar como future work** la integración harness+DSPy: nuestro harness define la orquestación, DSPy compila los prompts dentro de cada fase. Es el matrimonio natural.

---

## 7. Veredicto franco

- **Calidad del paper:** seminal. Bien escrito, programa de research duradero (DSPy se ha convertido en una herramienta estándar). Resultados empíricos sólidos en su dominio (NLP clásico).
- **Relevancia para nosotros:** **media-baja en ejecución, alta en framing.** DSPy resuelve un problema (prompt optimization) que no es nuestro cuello de botella actual. Nuestro cuello de botella es orquestación, contexto y HITL.
- **Lo mejor de DSPy para nosotros:** la **filosofía** (prompts como parámetros, no como strings fijos; metricas explícitas; compilación). No la implementación.
- **Riesgo principal:** migrar prematuramente, perder semanas en rewrite, no resolver los problemas duros del harness, y quedar amarrados a un framework externo en evolución.
- **Honestamente:** DSPy es un framework excelente para sistemas tipo QA/RAG/clasificación. Para harnesses de coding agents largos, con HITL, workspaces y artefactos persistentes, **no es el modelo mental correcto**. La integración natural (DSPy dentro de cada fase de nuestro harness) es interesante pero estrictamente future work.

**Acción concreta sugerida:**
1. Adoptar signatures explícitas en `prompts/*.md` como práctica de documentación.
2. Anotar "teleprompter-style demonstration selection" como evolución v2 de la mission case base del paper 02.
3. Citar DSPy en related work, no añadirlo como contender.
4. Formalizar métrica compuesta (AVSR, M-HIR, cost, entropy_delta) para tener algo medible aunque no optimicemos automáticamente.
