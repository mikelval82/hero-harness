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

## 3. Qué adoptamos en HERO y cómo está implementado

Reflexion propone *verbal reinforcement*: convertir el fallo en una reflexión causal que guía el siguiente intento. HERO lo implementa como gate disciplinario, no como framework aparte.

### Reflexión causal obligatoria antes de reintentar (diagnosis gate)
- **Del paper:** entre fallo y retry debe mediar una verbalización de la causa.
- **En HERO:** la fase REIMPLEMENT exige un bloque `## Diagnosis` validado por gate (`GATE_REQUIRED_MARKERS` en `src/core/gate.py`); el `audit.md` del reviewer se re-inyecta en el reintento (`src/mission/burst_runner.py`). No se reimplementa "a ciegas".

### Self-Verification del actor (Reflexion interna)
- **Del paper:** el actor reflexiona sobre su propia trayectoria.
- **En HERO:** el implementer produce una sección `## Self-Verification` obligatoria con sub-checks (acceptance, edge cases, evidencia), validada por gate (`src/core/gate.py`; `agents/implementer.md`).

### Memoria episódica corta y compactación
- **Del paper:** memoria verbal acotada (1-3 reflexiones) que mejora decisiones sin saturar contexto.
- **En HERO:** memoria por capas hot→cold con compactación automática al cerrar tarea (`compact_context` en `src/mission/burst_runner.py`, `prompts/compact-prompt.md`); solo hechos verificables pasan a `context-cold.md`.

### Failure signatures persistentes
- **Del paper:** etiquetar tipos de fallo para no repetirlos.
- **En HERO:** el reviewer tipifica `failure_type` (`src/core/gate.py`); el refiner detecta modos de fallo recurrentes con umbral (`REFINER_MIN_RECURRENCE=2` en `src/harness/refiner.py`); y la memoria de proyecto mantiene una sección "Recurring Failure Modes" (`PROJECT_MEMORY.md` vía `src/harness/project_memory.py`).

## 4. No adoptado (y por qué)

- **Self-generated tests como oracle de aceptación:** el propio paper muestra que generan false positives (MBPP); en HERO los tests del implementer son herramienta, no criterio de aceptación final, y no hay protocolo de tests adversariales pre-edición.
- **Límite semántico estricto de 1-3 reflexiones activas por tarea:** la compactación acota el contexto, pero no se impone un tope numérico de "lecciones activas".

---

## 5. Síntesis con papers previos

- **Paper 03 (AI Harness Engineering):** Reflexion es un mecanismo de feedback/control dentro del harness, no una arquitectura completa. Encaja como primitiva de recovery.
- **Paper 04 (Code as Agent Harness):** cae en memory + feedback-driven control; sus self-generated tests son una forma ligera de agent-initiated code artifact.
- **Paper 05 (Continual Harness):** Continual Harness generaliza Reflexion: no solo recuerda errores, tambien edita componentes del harness. Reflexion es trial-level; Continual Harness es harness-level.
- **Paper 06 (DSPy):** DSPy optimiza prompts offline/por compilacion; Reflexion optimiza comportamiento online via memoria verbal. Son ortogonales.
- **Paper 07 (Vesper):** ambos muestran que evidencia ejecutable + iteracion profunda puede superar generaciones baratas. Reflexion aporta el "why"; Vesper aporta el "spend more per iteration".
- **Paper 08 (Inference-Time Alignment):** Reflexion es guidance inference-time basado en trayectoria. Si la reflexion esta bien anclada, aumenta recoverability; si el evaluator produce false positives o la memoria induce local minima, amplifica el error.
