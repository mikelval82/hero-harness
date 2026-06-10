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

## 4. Mapeo a nuestro harness

| TextGrad | Nuestro harness | Diagnostico |
|----------|-----------------|-------------|
| `Variable` | `spec.md`, `plan.md`, `status.md`, codigo, tests, prompts, `agents/*.md` | Ya tenemos artefactos persistentes; falta declarar cuales son optimizables |
| `role_description` | Cabeceras/contratos de agentes y comandos | Implicito; deberia hacerse explicito |
| `requires_grad` | Permisos de edicion | Critico: user request y constraints NO deberian optimizarse |
| `Loss` | `audit.md`, tests, lints, user approval, cost | Existe, pero no siempre estructurado |
| `Gradient` | feedback causal del reviewer | Existe parcialmente; suele ser finalista, no propagado por variable |
| `TGD.step` | reimplementacion/refiner | Existe como comportamiento, no como interfaz |
| `Batch optimization` | aprender de muchas misiones aprobadas/rechazadas | Futuro: corpus de misiones |
| `Constraints` | reglas duras en AGENTS/CHECKPOINTS | Muy compatible |
| `Momentum` | ultimos intentos, contexto hot | Parcial |

**Posicion:** nuestro harness es ya un grafo TextGrad informal. Cada fase consume artefactos y produce otros. El reviewer calcula una loss verbal. La diferencia es que hoy no hacemos backpropagation explicito: el feedback se pasa al siguiente agente, pero no se asigna con precision a "esta variable fallo por esta razon".

---

## 5. Aplicabilidad — Harness

| Idea TextGrad | Coste | Beneficio | Impacto | Novedad |
|---------------|-------|-----------|---------|---------|
| **Estructurar `audit.md` como gradient report** por variable: artifact, role, objective, feedback, severity | Bajo | Alto | Alto | Media |
| **Role descriptions explicitas** en prompts/agentes/artefactos | Bajo | Medio-alto | Alto | Baja |
| **`requires_grad` conceptual**: que artefactos puede modificar cada fase | Bajo | Alto | Alto en seguridad | Media |
| **Refiner post-mision estilo TGD** para proponer ediciones a `agents/*.md` y `prompts/*.md` | Medio | Alto a largo plazo | Alto | Alta |
| **Batch prompt optimization** usando misiones pasadas | Alto | Alto si hay corpus | Alto | Media |
| **Momentum en reimplement loop**: incluir ultimos N intentos/fallos de la variable concreta | Bajo-medio | Medio | Medio | Baja |
| **Constraints NL en optimizadores** | Bajo | Alto | Alto | Baja |
| Meter TextGrad literal como dependencia | Medio-alto | Incierto | Medio | Baja |

### Cambio inmediato recomendado

Cambiar el formato del reviewer para que cada finding sea un gradiente sobre una variable:

```text
Variable: src/foo.py::parse_config
Role: parser de configuracion usado por MissionRunner
Objective: pasar tests y preservar compatibilidad
Feedback: la rama X rompe Y porque...
Suggested direction: separar validacion de normalizacion; no cambiar API publica
Constraints: no tocar src/core/state.py
```

Esto no requiere instalar TextGrad. Solo copia la parte buena: feedback causal, localizado y accionable.

### Donde encaja el refiner

TextGrad da una implementacion conceptual del **Refiner post-mision** que salia en Continual Harness:

1. Recoger misiones `APPROVED` / `REJECTED`.
2. Tratar `agents/*.md`, `prompts/*.md`, `commands/*.md` como variables.
3. Definir loss: failures recurrentes, coste, HITL innecesario, rejection rate.
4. Generar gradients por agente/prompt.
5. Proponer patch.
6. Humano aprueba.

La clave es que esto debe ser **offline y con aprobacion humana**, no auto-modificacion en vivo.

### Donde NO conviene aplicarlo

- No dejar que TextGrad optimice el requerimiento del usuario. El user request es input fijo, no variable.
- No optimizar prompts del harness durante una mision activa.
- No usar LLM-loss como oracle unico para codigo real.
- No dejar que un optimizer reescriba artefactos sin constraints explicitas.
- No confundir "feedback convincente" con feedback correcto.

---

## 6. Aplicabilidad — Paper / benchmark

| Uso | Valor |
|-----|-------|
| **Related work obligatoria** | Muy alto. Es el paper clave de "compound AI systems as optimizable computation graphs". |
| **Formalismo para nuestro metodo** | Alto. Podemos describir el harness como grafo de artefactos/fases con losses y gradients verbales. |
| **Baseline fuerte para code optimization** | Medio-alto. En LeetCode Hard supera Reflexion. |
| **Puente entre Reflexion y DSPy** | Alto. Reflexion = reflection por intento; DSPy = prompt/program optimization; TextGrad = autograd textual general. |
| **Justificacion de prompt optimization post-MVP** | Alto. Da vocabulario y resultados para futuro "harness optimizer". |
| **Contender MVP** | Dudoso. Implementarlo bien sube mucho coste y mezcla objetivos. Mejor como C4 opcional/subset. |

### Implicacion para contenders

Despues de leer Reflexion y TextGrad, el benchmark ideal tendria:

- **C1 Raw** — single-shot.
- **C2 Reflexion-style** — evaluate/reflect/retry con memoria corta.
- **C3 Harness** — nuestro pipeline multi-fase.
- **C4 TextGrad-style optimizer** — optimiza codigo/solucion con gradients y TGD.

Pero para MVP, C4 puede ser demasiado caro. Recomendacion pragmatica:

1. En MVP, redefinir C2 como Reflexion-style.
2. Citar TextGrad en related work.
3. Si hay presupuesto, anadir C4 solo en un subset de coding challenges, no en todo el benchmark.

Si C3 gana a C2 pero no se compara con TextGrad, el paper sigue defendible, pero habra que explicar que TextGrad es un **optimizer interno posible**, no un workflow completo con workspace, HITL, permissions y artefactos.

---

## 7. Riesgos y caveats

1. **La analogia con backprop puede seducir demasiado.** No hay gradientes reales, ni continuidad, ni garantia de convergencia. Hay criticas textuales.
2. **El evaluator manda.** Si la loss esta mal definida, el "gradiente" optimiza hacia el error. Esto conecta directo con paper 08.
3. **Coste alto.** Loss + gradient + update por iteracion se multiplica rapido. En sistemas con muchos edges, el overhead puede dominar.
4. **Optimiza lo que sabe verbalizar.** En codigo, si el fallo depende de un edge case no observado, el gradiente puede sonar bien y aun asi ser falso.
5. **High-stakes domains son solo proof-of-concept.** Moleculas y radioterapia requieren validacion experimental/clinica.
6. **Role descriptions son hand-crafted.** TextGrad se vende como general, pero la descripcion de variables y objective prompts siguen siendo diseño de harness.
7. **Riesgo de overfitting al evaluator.** Especialmente con LLM-as-judge o local tests incompletos.

---

## 8. Decisiones recomendadas

### Para el harness

1. **Adoptar vocabulario TextGrad en docs internas:** variable, role, loss, gradient, optimizer, constraints, momentum.
2. **Modificar `reviewer.md`** para producir feedback localizado por variable/artefacto, no solo lista de findings globales.
3. **Anadir role descriptions a artefactos:** `spec.md` como contrato, `plan.md` como estrategia editable, `status.md` como outcome, codigo como implementation variable.
4. **Marcar conceptualmente `requires_grad`:** que puede editar cada agente y que es inmutable.
5. **Disenar un Refiner post-mision** inspirado en TGD, con aprobacion humana, para mejorar prompts/agentes a partir de failures recurrentes.
6. **No introducir TextGrad como dependencia ahora.** Copiar el modelo mental primero; evaluar libreria despues.

### Para el paper

1. **Citar TextGrad en related work** como marco de automatic differentiation via text para compound AI systems.
2. **Usar su formalismo para describir nuestro harness**: fases como funciones, artefactos como variables, reviewer/tests como loss, audit como gradient.
3. **Diferenciarnos claramente:** TextGrad optimiza variables; nuestro harness orquesta trabajo de software con roles, permisos, workspace, HITL, context layering y review.
4. **Anadir C4 TextGrad-style solo si hay presupuesto.** Si no, presentarlo como prior art/future baseline.
5. **Usar sus resultados de LeetCode Hard** para justificar que Reflexion no es el unico baseline fuerte: TextGrad ya mejora Reflexion en code optimization.

---

## 9. Veredicto franco

TextGrad es **muy relevante**. De todos los papers hasta ahora, es el que mejor convierte "feedback del reviewer" en una primitiva formal. Reflexion nos dio el loop `fail -> reflect -> retry`; TextGrad lo escala a `loss -> backward -> gradients por variable -> optimizer.step`.

La buena noticia: nuestro harness ya esta muy cerca del modelo mental de TextGrad. La mala: aun no lo explota. Hoy pasamos feedback de una fase a otra, pero no lo propagamos quirurgicamente hacia los artefactos responsables del fallo.

**Lo mas importante que aporta:**

1. Vocabulario para formalizar el harness como grafo computacional.
2. Un formato disciplinado para `audit.md` como gradiente textual.
3. Una ruta clara hacia refiner post-mision.
4. Un baseline fuerte para code optimization que supera Reflexion.

**Accion concreta sugerida:**

1. Reescribir el formato del reviewer para emitir gradients por variable.
2. Tratar el reimplement loop como `optimizer.step`, con constraints explicitas.
3. Adoptar `requires_grad` conceptual para proteger inputs del usuario y reglas duras.
4. Incluir TextGrad como related work central y C4 opcional en benchmark.

---

## 10. Sintesis con papers previos

- **Paper 06 (DSPy):** DSPy optimiza programas/prompts con demonstrations; TextGrad optimiza variables via feedback textual. Son complementarios: DSPy demos + TextGrad instruction optimization mejora GSM8K.
- **Paper 09 (Reflexion):** Reflexion es un caso particular de TextGrad con una sola trayectoria/solucion y una reflexion como feedback. TextGrad generaliza a grafos y separa gradient engine de optimizer.
- **Paper 05 (Continual Harness):** el Refiner de Continual Harness podria implementarse como TGD sobre componentes `(p, G, K, M)`.
- **Paper 08 (Inference-Time Alignment):** TextGrad es guidance inference-time. Si la loss/evaluator esta mal, amplifica errores; si esta anclada en evidencia, mejora recoverability.
- **Paper 07 (Vesper):** ambos apoyan "quality per iteration" sobre retries baratos. TextGrad profundiza cada iteracion con loss/gradient/update; Vesper lo hace con coding agents y DB/evaluation loop.
- **Paper 04 (Code as Agent Harness):** TextGrad formaliza los artefactos del agente como variables optimizables dentro del harness.
- **Paper 03 (AI Harness Engineering):** da una posible implementacion concreta para el componente de optimization/control que paper 03 describe de forma mas general.
