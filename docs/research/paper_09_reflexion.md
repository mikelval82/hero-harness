# Paper 09 — Reflexion: Language Agents with Verbal Reinforcement Learning

**Autores:** Noah Shinn, Federico Cassano, Edward Berman, Ashwin Gopinath, Karthik Narasimhan, Shunyu Yao.
**arXiv:** 2303.11366v4, octubre 2023.
**Tipo:** Framework empirico de self-reflection + experimentos en decision-making, reasoning y programacion.
**Archivo:** `papers/Reflexion - language agents with verbal reinforcement learning.pdf`

---

## 1. Tesis del paper en una frase

Reflexion convierte feedback escalar/binario de una tarea en **feedback verbal persistente**: el agente falla, evalua la trayectoria, genera una reflexion en lenguaje natural, la guarda en memoria episodica y reintenta condicionado por esa leccion. Es **RL sin actualizar pesos**: la politica no cambia por gradient descent, cambia porque el contexto del agente contiene memoria de errores pasados.

Para nuestro trabajo, Reflexion es la baseline historica obligatoria para cualquier afirmacion sobre "el agente mejora via review/retry". No es un harness multi-fase como el nuestro, pero si es el ancestro directo del patron `evaluate -> reflect -> retry`.

---

## 2. Piezas operativas clave

### 2.1 Arquitectura Actor / Evaluator / Self-Reflection

| Componente | Funcion | Equivalente nuestro |
|------------|---------|---------------------|
| **Actor** (`Ma`) | Genera acciones, razonamiento o codigo condicionado por observacion + memoria | `implementer`, o el agente activo dentro de una fase |
| **Evaluator** (`Me`) | Puntua la trayectoria/salida con reward binario, heuristica, exact match, tests, compilador o LLM | `reviewer`, tests, linters, acceptance criteria |
| **Self-Reflection** (`Msr`) | Traduce fallo + trayectoria + memoria en una leccion verbal accionable | No existe como fase explicita; esta mezclado en `audit.md`, `status.md`, reimplement prompts |
| **Memory** (`mem`) | Buffer de reflexiones pasadas, normalmente limitado a 1-3 experiencias | `context-hot.md` / `context-cold.md`, pero no centrado en errores por intento |

La idea central: el reward escalar no es directamente util para un LLM, asi que se "amplifica" a lenguaje natural. La reflexion funciona como **gradiente semantico**: no dice solo "fallaste", dice "fallaste porque buscaste el objeto equivocado / el test no cubre el orden / asumiste una profesion comun incorrecta".

### 2.2 Loop de Reflexion

1. El Actor produce una trayectoria o solucion inicial.
2. El Evaluator devuelve una senal de exito/fallo.
3. El Self-Reflection model produce una reflexion verbal sobre el fallo.
4. La reflexion se guarda en memoria.
5. El Actor reintenta con esa memoria en el prompt.
6. Se repite hasta exito o limite de trials.

Dos detalles importantes:

- La memoria se limita por ventana deslizante (`1-3` reflexiones) para no contaminar contexto.
- Reflexion resetea el entorno entre trials; no es reset-free como Continual Harness.

### 2.3 Tres dominios evaluados

| Dominio | Setup | Resultado reportado |
|---------|-------|---------------------|
| **ALFWorld** | ReAct + reflexion sobre tareas textuales multi-step | `130/134` tareas resueltas; mejora absoluta ~22% frente a ReAct |
| **HotPotQA** | CoT/ReAct + exact match como reward binario | Mejora ~20% sobre baselines; self-reflection supera a memoria episodica cruda |
| **Programacion** | HumanEval, MBPP, Rust via MultiPL-E, LeetcodeHardGym | HumanEval Python `80% -> 91%`; Rust `60% -> 68%`; Leetcode Hard `7.5% -> 15%` |

### 2.4 Programacion: lo mas relevante para nosotros

Reflexion usa self-generated unit tests como Evaluator interno:

1. Genera implementacion.
2. Genera hasta 6 tests con CoT.
3. Filtra tests sintacticamente validos via AST.
4. Ejecuta tests.
5. Si fallan, genera reflexion verbal y reintenta.

La ablation en HumanEval Rust es muy informativa:

| Variante | Test generation | Self-reflection | Pass@1 |
|----------|-----------------|-----------------|--------|
| Base model | No | No | `0.60` |
| Sin tests, con reflection | No | Si | `0.52` |
| Con tests, sin reflection | Si | No | `0.60` |
| Reflexion completo | Si | Si | `0.68` |

Interpretacion: **los tests solos detectan errores pero no los convierten en una mejora util**; la reflection sola puede empeorar si no esta anclada en evidencia. La ganancia viene de la combinacion: evidencia ejecutable + verbalizacion del fallo.

### 2.5 Limitaciones identificadas por el propio paper

- **Local minima:** Reflexion puede repetir una estrategia equivocada si la reflexion no induce exploracion real.
- **WebShop falla:** en tareas con busqueda ambigua y necesidad de comportamientos muy diversos, ReAct + Reflexion no mejora significativamente.
- **Dependencia de capacidad:** con `starchat-beta`, HumanEval queda `0.26 -> 0.26`; la habilidad de formular self-corrections utiles aparece en modelos suficientemente fuertes.
- **False positives de tests:** si los tests generados pasan una solucion incorrecta, el agente termina prematuramente. En MBPP Python el falso positivo reportado es mucho mayor que en HumanEval Python.
- **TDD no cubre todo:** funciones impuras, no determinismo, APIs externas, hardware, concurrencia y paralelismo son malos candidatos para self-generated tests como unico oracle.

---

## 3. Mapeo a nuestro harness

| Reflexion | Nuestro harness | Diagnostico |
|-----------|-----------------|-------------|
| Actor | `implementer` | Encaja directo |
| Evaluator | `reviewer` + tests + comandos | Tenemos evaluador mas rico, pero no siempre produce reward estructurado |
| Self-Reflection model | No hay fase aislada | Gap claro: `audit.md` informa, pero no se destila siempre a "lesson learned" reutilizable |
| Episodic memory | `context-hot.md` y compactacion a `context-cold.md` | Similar, pero nuestra memoria mezcla hallazgos, decisiones y resultados; no distingue reflexiones por fallo |
| Max 1-3 reflections | No tenemos limite semantico por tipo de experiencia | Riesgo de contexto largo y difuso |
| Retry loop | `reviewer -> reimplement` | Ya existe, pero Reflexion sugiere que el retry debe pasar por una verbalizacion causal del fallo |
| Self-generated tests | Tests escritos por implementer, si procede | No hay protocolo explicito de generar tests adversariales antes de editar |
| Heuristicas de fallo | Parciales en `CHECKPOINTS.md` y reviewer | Podriamos formalizar failure signatures |

**Posicion:** nuestro harness ya contiene Reflexion de forma implicita, pero distribuida entre fases. Lo que falta no es "hacer retry"; lo que falta es una unidad explicita de **verbal reinforcement** entre fallo y reintento.

---

## 4. Aplicabilidad — Harness

| Idea Reflexion | Coste | Beneficio | Impacto | Novedad |
|----------------|-------|-----------|---------|---------|
| **Reflection step explicito tras REJECTED**: antes de reimplementar, producir `reflection.md` o seccion en `status.md` con causa, evidencia y cambio de estrategia | Bajo | Alto | Alto | Baja-media |
| **Convertir `audit.md` en lecciones compactas** para `context-hot.md`: "No volver a hacer X; evidencia Y; proximo intento Z" | Bajo | Alto | Alto | Baja |
| **Failure signatures** (`test_false_positive`, `wrong_assumption`, `insufficient_exploration`, `overfit_acceptance`, `tool_failure`) | Bajo | Medio-alto | Alto | Media |
| **Self-generated tests como advisory oracle** antes de final review | Medio | Medio | Alto en bug-fix/coding tasks | Baja |
| **Limite de memoria reflexiva**: max 1-3 lecciones activas por tarea | Bajo | Medio | Medio | Baja |
| **Reflexion baseline** en benchmark | Medio | Alto | Alto | Baja, pero metodologicamente necesaria |
| Usar LLM evaluator para todo | Bajo | Bajo / Riesgoso | Medio | Baja |

### Cambio pequeno pero potente

En el loop actual, cuando `reviewer` rechaza, no basta con pasar el `audit.md` al siguiente implementer. Conviene obligar al implementer a escribir una micro-reflexion antes de tocar codigo:

```text
Failure:
- Que fallo exactamente.
- Que evidencia lo demuestra.
- Que asuncion mia fue incorrecta.
- Que cambiare en el siguiente intento.
- Que NO debo tocar.
```

Esto copia el mecanismo de Reflexion sin convertir el harness entero en otro framework.

### Donde NO conviene copiar Reflexion literal

- No usar self-generated tests como criterio de aceptacion final. Deben ser herramienta de exploracion, no oracle.
- No dejar que reflexiones genericas entren en `context-cold.md`; solo lecciones causales y verificables.
- No aplicar retries ilimitados. Reflexion funciona con ventanas pequenas; el crecimiento de contexto degrada.
- No confundir "memoria de fallo" con "memoria de todo". La reflexion util es comprimida, causal y accionable.

---

## 5. Aplicabilidad — Paper / benchmark

| Uso | Valor |
|-----|-------|
| **Related work obligatoria** | Alto. Reflexion es el prior art canonico de verbal self-improvement en agentes LLM. |
| **Baseline metodologica** | Muy alto. Un contender "Raw + Reflexion loop" separaria la ganancia de simple retry/reflection de la ganancia del harness multi-fase. |
| **Argumento para nuestra memoria hot/cold** | Medio. Reflexion demuestra que memoria verbal corta puede mejorar decision-making, pero no prueba memoria cross-mision. |
| **Advertencia sobre generated tests** | Alto. Su fallo en MBPP Python es una cita perfecta para justificar hidden tests y oracles externos. |
| **Cita de capability-dependence** | Medio-alto. StarChat no mejora; modelos fuertes si. Conecta con paper 05 y paper 08. |
| **SOTA cuantitativo actual** | Bajo. Los numeros son de 2023; no usarlos como SOTA moderno, sino como evidencia historica del mecanismo. |

### Implicacion para contenders

El research plan actual tiene:

- C1 Raw
- C2 Loop tonto
- C3 Harness

Reflexion sugiere que C2 deberia ser mas preciso. Dos opciones:

1. **Mantener C2 como loop tonto** y anadir C2b = Reflexion-style loop.
2. **Redefinir C2** como `Raw + evaluate + reflect + retry`, con mismo budget que C3.

La segunda opcion es mas limpia si el presupuesto es limitado. Si C3 gana a C2-Reflexion, entonces el paper puede afirmar que el valor no viene solo de "reintentar con feedback", sino de la estructura multi-fase del harness.

---

## 6. Riesgo / beneficio / impacto / novedad

### 6.1 Como aporte al harness

La integracion de Reflexion es de **alto ROI** porque no requiere arquitectura nueva. Nuestro reviewer ya produce feedback; nuestros implementers ya reintentan; nuestro context layer ya persiste informacion. Falta una pequena pieza disciplinaria: convertir cada fallo en una reflexion causal antes del siguiente intento.

**Beneficio esperado:** menos retries que repiten el mismo patron, mejor aprovechamiento de `audit.md`, y mejor compactacion post-mision.

**Riesgo:** si la reflexion se genera sin evidencia, amplifica la narrativa equivocada. Esto conecta directamente con paper 08: guidance solo ayuda si el evaluator y la regla de guidance tienen retention gap positivo. Un `reflection.md` basado en tests falsos o en un audit superficial puede empeorar el siguiente intento.

### 6.2 Como aporte al paper

Reflexion es el baseline que cualquier reviewer preguntara: "Como se compara vuestro harness con un simple self-reflection loop?". No basta con compararnos contra Raw. Hay que mostrar que la estructura de agentes especializados, artefactos y review independiente aporta algo por encima de Reflexion.

### 6.3 Novedad

Como idea, Reflexion ya es clasico. La novedad no esta en usarlo; esta en:

- meterlo como **componente interno** de un harness de ingenieria,
- medirlo contra un harness multi-fase real,
- separar reflection textual de oracles ejecutables,
- estudiar coste/beneficio bajo budget de tokens.

---

## 7. Decisiones recomendadas

### Para el harness

1. **Anadir un reflection checkpoint tras cada REJECTED**: el implementer debe destilar `audit.md` en causa, evidencia, cambio de estrategia y non-goals antes de editar.
2. **Persistir solo reflexiones verificables** en `context-hot.md`; compactarlas a `context-cold.md` solo si describen un patron reutilizable.
3. **Extender `reviewer.md`** para etiquetar el tipo de fallo: wrong assumption, missing test, overfit, regression, unclear spec, tool/env issue.
4. **Permitir self-generated tests como herramienta**, pero no como acceptance. Reportar false positives si se usan en benchmark.
5. **Limitar memoria reflexiva activa** a las ultimas 1-3 lecciones por tarea para evitar que el prompt se convierta en un archivo de arrepentimientos.

### Para el paper

1. **Citar Reflexion en related work** como prior art central de verbal reinforcement learning.
2. **Incluir un contender Reflexion-style** o redefinir C2 como `Raw + reflect/retry`. Es el control metodologico mas importante tras Raw.
3. **Usar sus limitaciones sobre generated tests** para justificar test suites ocultas, sandboxing y evaluadores externos.
4. **No vender sus numeros como SOTA actual**. Usarlos como evidencia de mecanismo, no como estado del arte de 2026.
5. **Conectar con paper 08**: Reflexion es una instancia concreta de inference-time guidance; ayuda cuando la reflexion esta anclada en evidencia, falla cuando induce local minima o false positives.

---

## 8. Veredicto franco

Reflexion es **menos avanzado que nuestro harness**, pero es **metodologicamente peligroso ignorarlo**. Si nuestro paper compara solo contra Raw, un reviewer puede decir: "quizas todo el beneficio viene de retry + self-reflection". Reflexion es exactamente ese baseline.

Su aportacion mas valiosa para nosotros no es el resultado de HumanEval `91%` de 2023. Es la demostracion de que hay una diferencia real entre:

- ejecutar tests y volver a intentar a ciegas,
- y convertir el fallo en una explicacion causal que guia el siguiente intento.

Esa distincion encaja perfectamente con nuestro `reviewer -> reimplement`, pero hoy no esta formalizada.

**Accion concreta sugerida:**

1. Convertir C2 del benchmark en **Reflexion-style loop**: generar, evaluar, reflexionar, reintentar con memoria corta.
2. Introducir `reflection` como paso obligatorio tras `REJECTED` en el harness.
3. Mantener tests generados como herramienta auxiliar, nunca como oracle final.
4. Citar Reflexion junto a ReAct/Self-Refine en related work, y diferenciarlo claramente: Reflexion optimiza una politica por memoria verbal; nuestro trabajo evalua una metodologia de orquestacion multi-fase con roles, artefactos, HITL y coste.

---

## 9. Sintesis con papers previos

- **Paper 03 (AI Harness Engineering):** Reflexion es un mecanismo de feedback/control dentro del harness, no una arquitectura completa. Encaja como primitiva de recovery.
- **Paper 04 (Code as Agent Harness):** cae en memory + feedback-driven control; sus self-generated tests son una forma ligera de agent-initiated code artifact.
- **Paper 05 (Continual Harness):** Continual Harness generaliza Reflexion: no solo recuerda errores, tambien edita componentes del harness. Reflexion es trial-level; Continual Harness es harness-level.
- **Paper 06 (DSPy):** DSPy optimiza prompts offline/por compilacion; Reflexion optimiza comportamiento online via memoria verbal. Son ortogonales.
- **Paper 07 (Vesper):** ambos muestran que evidencia ejecutable + iteracion profunda puede superar generaciones baratas. Reflexion aporta el "why"; Vesper aporta el "spend more per iteration".
- **Paper 08 (Inference-Time Alignment):** Reflexion es guidance inference-time basado en trayectoria. Si la reflexion esta bien anclada, aumenta recoverability; si el evaluator produce false positives o la memoria induce local minima, amplifica el error.
