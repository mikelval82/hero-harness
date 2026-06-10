# Paper 10 — TextGrad: Automatic "Differentiation" via Text

**Autores:** Mert Yuksekgonul, Federico Bianchi, Joseph Boen, Sheng Liu, Zhi Huang, Carlos Guestrin, James Zou (Stanford / CZ Biohub).
**arXiv:** 2406.07496v1, junio 2024.
**Tipo:** Framework de optimizacion de sistemas compuestos + experimentos en codigo, QA, prompt optimization, moleculas y radioterapia.
**Archivo:** `papers/TEXTGRADO - automatic differentiation via text.pdf`

---

## 1. Tesis del paper en una frase

Los sistemas modernos de IA ya no son solo modelos: son **sistemas compuestos** con LLMs, tools, simuladores, evaluadores, prompts y artefactos intermedios. TextGrad propone tratarlos como **grafos computacionales** y hacer "backpropagation" no con gradientes numericos, sino con **feedback textual generado por LLMs**. Cada prompt, codigo, solucion, molecula o hiperparametro se vuelve una variable optimizable.

Para nosotros: TextGrad es la formalizacion mas limpia de una intuicion central del harness: `audit.md` no deberia ser solo una opinion final; deberia funcionar como **gradiente textual** propagado hacia las piezas concretas que causaron el fallo.

---

## 2. Piezas operativas clave

### 2.1 Variables, funciones, loss y gradients

TextGrad imita la abstraccion de PyTorch:

| PyTorch | TextGrad | Ejemplo |
|---------|----------|---------|
| `Tensor` | `tg.Variable` | prompt, solucion, codigo, SMILES, hiperparametros |
| `Module` / function | `LLMCall`, simulator, evaluator, tool | llamada a LLM, tests, AutoDock Vina, matRad |
| `Loss` | `TextLoss` o evaluador externo | "critica este codigo", exact match, docking score |
| `loss.backward()` | backprop textual | generar feedback sobre variables predecesoras |
| `optimizer.step()` | `TextualGradientDescent` | reescribir la variable usando feedback |

Cada `Variable` tiene:

- **value**: el texto o artefacto actual.
- **role_description**: que papel juega la variable en el sistema.
- **gradients**: criticas textuales acumuladas.
- **predecessors**: variables que produjeron esta variable.
- **requires_grad**: si esa variable puede recibir feedback y ser optimizada.

El detalle mas importante es `role_description`. El paper muestra que el optimizador cambia de comportamiento segun si una variable se describe como "final numerical answer", "reasoning and final prediction" o "system prompt". Esto es directamente relevante para nuestros artefactos.

### 2.2 Backward mode — el LLM como motor de gradientes

Para una llamada:

```text
Prompt + Question -> LLM -> Prediction -> Evaluator -> Loss
```

TextGrad primero genera feedback sobre `Prediction`, y despues propaga feedback hacia `Prompt` explicando como modificarlo para mejorar la loss downstream. El gradiente no es un numero; es una critica:

> "Esta prediccion falla porque...", "cambiar X por Y resolveria...", "anadir una instruccion para verificar Z..."

El backward engine tiene una regla importante: **no propone la nueva variable**. Solo da feedback. La reescritura la hace el optimizador.

### 2.3 Textual Gradient Descent (TGD)

`TGD.step(variable, gradients)` llama a un LLM para producir una version mejorada de la variable. Separan dos roles:

| Rol | Responsabilidad |
|-----|-----------------|
| **Gradient engine** | Criticar, diagnosticar, explicar cambios necesarios |
| **Optimizer** | Aplicar esas criticas y emitir la variable nueva |

Esta separacion es buena arquitectura. Evita mezclar "que esta mal" con "reescribe todo ahora", que es exactamente una fuente de degradacion en loops de reimplementacion.

### 2.4 Instance optimization vs prompt optimization

| Modo | Que se optimiza | Analogos nuestros |
|------|-----------------|-------------------|
| **Instance optimization** | Una solucion concreta en test-time: codigo, respuesta, molecula, plan medico | `implementer` arreglando una tarea concreta |
| **Prompt optimization** | Un prompt reusable que mejora muchas instancias | editar `agents/*.md`, `prompts/*.md`, `commands/*.md` |

Esto separa dos horizontes que en nuestro harness conviene no mezclar:

- **Dentro de la mision:** optimizar artefactos de la tarea.
- **Entre misiones:** optimizar el harness mismo.

### 2.5 Extensiones de optimizacion

| Tecnica | Implementacion TextGrad | Traduccion al harness |
|---------|-------------------------|------------------------|
| **Batch optimization** | `tg.sum(losses)` concatena gradients de multiples ejemplos | optimizar prompts con corpus de misiones |
| **Constraints** | restricciones NL que el optimizador debe preservar | "no tocar API publica", "no cambiar user intent", "zero footprint" |
| **Momentum** | incluir iteraciones pasadas de la variable | recordar los ultimos N intentos fallidos |
| **In-context examples** | ejemplos de variables buenas | misiones aprobadas como demonstrations |

El coste tambien importa: para un grafo con `n` edges, cada iteracion puede hacer hasta `n` llamadas extra para gradients. En los experimentos de codigo, cada iteracion usa 3 llamadas a GPT-4o: loss, gradient, update.

---

## 3. Resultados principales

### 3.1 Code optimization — LeetCode Hard

Setup:

- Dataset LeetCode Hard de Reflexion.
- 39 problemas, 5 seeds, 5 iteraciones.
- Evaluacion real via LeetCode hidden tests.
- TextGrad usa zero-shot; Reflexion usa 1 demostracion.

| Metodo | Completion Rate |
|--------|-----------------|
| Zero-shot gpt-4o | `0.26` |
| Reflexion, 1 demo, 5 iteraciones | `0.31 ± 0.012` |
| **TextGrad, 0 demos, 5 iteraciones** | **`0.36 ± 0.018`** |

El punto fuerte: mejora a Reflexion con menos hand-holding. El punto debil: mas llamadas por iteracion y una evaluacion bastante especializada.

### 3.2 Solution optimization — GPQA / MMLU

TextGrad optimiza la **solucion de una pregunta concreta** en test-time. Usa un objective tipo "critica creativamente esta respuesta, busca por que podria ser incorrecta" y aplica 3 actualizaciones.

| Dataset | Baseline | TextGrad |
|---------|----------|----------|
| GPQA Diamond | CoT `51.0`, best reported `53.6` | **`55.0`** |
| MMLU Machine Learning | `85.7` | **`88.4`** |
| MMLU College Physics | `91.2` | **`95.1`** |

Esto es Reflexion generalizado: no solo "aprende del fallo"; trata la respuesta como variable y la optimiza por pasos.

### 3.3 Prompt optimization — reasoning

Setup:

- Forward model barato: `gpt-3.5-turbo-0125`.
- Gradient engine fuerte: `gpt-4o`.
- Batch size 3, 12 iteraciones.
- TextGrad optimiza solo instrucciones, sin demonstrations.

| Dataset | CoT 0-shot | DSPy BFSR, 8 demos | TextGrad, instruction-only |
|---------|------------|--------------------|----------------------------|
| Object Counting | `77.8` | `84.9` | **`91.9`** |
| Word Sorting | `76.7` | **`79.8`** | **`79.8`** |
| GSM8K | `72.9` | **`81.1`** | **`81.1`** |

Hallazgo muy util: DSPy y TextGrad son complementarios. DSPy selecciona demonstrations; TextGrad optimiza instrucciones. En GSM8K, combinar demos de DSPy con prompt de TextGrad sube a `82.1`.

### 3.4 Molecule optimization

TextGrad optimiza SMILES strings con una loss multiobjetivo:

- binding affinity via AutoDock Vina / DOCKSTRING;
- druglikeness via QED / RDKit.

Resultados:

- 58 targets de DOCKSTRING.
- 3 fragmentos iniciales.
- 10 iteraciones por target.
- Para 29 targets con drugs aprobados, genera moleculas con scores competitivos frente a moleculas clinicas, segun la misma funcion in silico.

Esto es prueba de generalidad, no evidencia clinica. El propio paper reconoce que validacion experimental queda fuera de scope.

### 3.5 Radiotherapy treatment planning

TextGrad optimiza los hiperparametros del optimizador numerico interno (`matRad`) para planes de radioterapia:

- variable: pesos para PTV y organos en riesgo;
- inner loop: optimizador numerico genera plan;
- loss: LLM evalua el plan contra protocolos clinicos;
- optimizer: actualiza pesos con momentum/proyeccion suave usando ejemplos clinicos.

Resultados sobre 5 pacientes de cancer de prostata:

- mejores metricas de dosis media y `D95` para PTV que planes clinicos;
- menor dosis media en vejiga y recto;
- proof-of-concept, no validacion clinica.

---

## 4. Qué adoptamos en HERO y cómo está implementado

TextGrad modela un sistema compuesto como grafo de variables optimizables con "gradientes" textuales. HERO ya es, en la práctica, un grafo de este tipo y materializa varias de sus primitivas.

### Gradientes textuales por hallazgo (audit como gradiente)
- **Del paper:** la loss del evaluador se propaga como feedback causal localizado por variable.
- **En HERO:** el reviewer emite una sección `### Gradient Findings` (campo `textual_gradients` en `audit.md`) validada por gate en REVIEW (`src/core/gate.py`); su protocolo convierte cada problema en un gradiente textual (`agents/reviewer.md`).

### requires_grad / no_grad y permisos por fase
- **Del paper:** marcar qué variables son optimizables y cuáles fijas (`requires_grad`).
- **En HERO:** cada agente declara una sección `## Signature` con inputs/outputs y `requires_grad`/`no_grad`; los permisos de herramienta por fase lo refuerzan (REVIEW no tiene Edit: `DEFAULT_TOOLS`/`IMPL_TOOLS`/`REVIEW_TOOLS` en `src/core/context.py`). El user request y las reglas duras quedan como input fijo.

### optimizer.step = reimplement loop
- **Del paper:** `TGD.step` actualiza la variable a partir del gradiente.
- **En HERO:** el bucle REIMPLEMENT re-inyecta el `audit.md` y exige `## Diagnosis` antes de editar (`src/mission/burst_runner.py`, gate en `src/core/gate.py`), con constraints explícitas.

### Refiner post-misión estilo TGD (offline, con aprobación humana)
- **Del paper:** optimizar prompts/componentes a partir de la loss agregada.
- **En HERO:** el refiner trata `agents/*.md`/`prompts/*.md` como variables y propone parches (`refiner-proposal.md`) solo si hay fallos recurrentes (`REFINER_MIN_RECURRENCE=2` en `src/harness/refiner.py`); es offline y requiere aprobación humana (`commands/refine-harness.md`, `research_plan/refiner_post_mission.md`). No hay auto-modificación en vivo.

## 5. No adoptado (y por qué)

- **Batch optimization sobre un corpus de misiones:** existe una case base por similitud de tokens (`src/harness/case_base.py`), pero no se optimizan prompts en lote vía gradientes agregados.
- **TextGrad como dependencia/librería literal:** se adopta el modelo mental (variable/loss/gradient/constraints), no el paquete.
- **Momentum formal por variable:** el contexto hot aporta los últimos intentos, pero no se implementa un término de momentum por variable concreta.

---

## 6. Sintesis con papers previos

- **Paper 06 (DSPy):** DSPy optimiza programas/prompts con demonstrations; TextGrad optimiza variables via feedback textual. Son complementarios: DSPy demos + TextGrad instruction optimization mejora GSM8K.
- **Paper 09 (Reflexion):** Reflexion es un caso particular de TextGrad con una sola trayectoria/solucion y una reflexion como feedback. TextGrad generaliza a grafos y separa gradient engine de optimizer.
- **Paper 05 (Continual Harness):** el Refiner de Continual Harness podria implementarse como TGD sobre componentes `(p, G, K, M)`.
- **Paper 08 (Inference-Time Alignment):** TextGrad es guidance inference-time. Si la loss/evaluator esta mal, amplifica errores; si esta anclada en evidencia, mejora recoverability.
- **Paper 07 (Vesper):** ambos apoyan "quality per iteration" sobre retries baratos. TextGrad profundiza cada iteracion con loss/gradient/update; Vesper lo hace con coding agents y DB/evaluation loop.
- **Paper 04 (Code as Agent Harness):** TextGrad formaliza los artefactos del agente como variables optimizables dentro del harness.
- **Paper 03 (AI Harness Engineering):** da una posible implementacion concreta para el componente de optimization/control que paper 03 describe de forma mas general.
