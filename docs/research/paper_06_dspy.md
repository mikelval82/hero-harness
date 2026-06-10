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

## 3. Qué adoptamos en HERO y cómo está implementado

HERO toma de DSPy la **filosofía** (programa declarativo de módulos con signatures y un pipeline explícito), no el framework ni el compiler.

### Signatures NL-typed por agente
- **De DSPy:** cada módulo declara una signature con campos de input/output.
- **En HERO:** cada agente declara una sección `## Signature` con `role`, `inputs`, `outputs`, `responsibilities` y artefactos `editable (requires_grad)` / `read_only (no_grad)` — ver `agents/reviewer.md`, `agents/implementer.md`, etc. Son signatures en lenguaje natural, no tipado formal.

### Módulos + pipeline como grafo declarativo
- **De DSPy:** los módulos se componen en un pipeline (grafo computacional).
- **En HERO:** los agentes son los módulos; `PhaseConfig` + `PHASE_REGISTRY` (`src/core/context.py`) declaran para cada fase su `template`, sus `includes` (artefactos de entrada) y su `gate` (salida verificada). `src/harness/prompt_renderer.py` (`render_prompt`) sustituye los includes en el template. El pipeline concreto se compone según el modo (`MISSION_PIPELINES`).

### Métrica de éxito como gate (no numérica)
- **De DSPy:** una métrica guía la compilación.
- **En HERO:** el "score" es el veredicto `APPROVED` del reviewer más los Deterministic Checks (`DC*`), validados por gate (`src/core/gate.py`). Es una señal de éxito explícita, aunque no un score numérico que se optimice automáticamente.

## 4. No adoptado (y por qué)

- **Teleprompter / compiler (BootstrapFewShot, MIPRO):** no hay optimización automática de prompts. Requeriría un corpus grande de misiones (≥30) y métricas baratas evaluables muchas veces.
- **Bootstrap de demonstraciones few-shot:** existe retrieval por similitud (case base, paper 02), pero no selección de demostraciones guiada por métrica.
- **Métrica numérica de optimización:** el éxito es `APPROVED` + DC checks, no un score escalar que un optimizador maximice.
- **Migrar al framework DSPy:** el coste excede el beneficio; DSPy asume pipelines in-memory tipo QA/RAG y no tiene primitivas naturales para workspace en disco, HITL, reimplement loop ni jerarquía mission/task/burst.
