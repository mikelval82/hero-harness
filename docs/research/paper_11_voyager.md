# Paper 11 — Voyager: An Open-Ended Embodied Agent with Large Language Models

**Autores:** Guanzhi Wang, Yuqi Xie, Yunfan Jiang, Ajay Mandlekar, Chaowei Xiao, Yuke Zhu, Linxi "Jim" Fan, Anima Anandkumar (NVIDIA, Caltech, UT Austin, Stanford, UW Madison).
**arXiv:** 2305.16291v2, octubre 2023.
**Tipo:** Sistema de agente embodied lifelong learning en Minecraft + evaluacion empirica con ablations.
**Archivo:** `papers/VOYAGER - an open-ended embodied agent with large language models.pdf`

---

## 1. Tesis del paper en una frase

VOYAGER demuestra que un agente LLM puede aprender de forma **open-ended** si se le da una arquitectura con tres piezas: un **curriculo automatico** que propone tareas alcanzables y novedosas, una **skill library** de codigo ejecutable reusable, y un loop de **iterative prompting** que incorpora feedback del entorno, errores de ejecucion y self-verification antes de guardar nuevas habilidades.

Para nuestro trabajo: Voyager no es un harness de software engineering, pero es probablemente el paper mas claro sobre **como convertir ejecuciones exitosas en habilidades reutilizables**. Es la version embodied de una idea que nos interesa mucho: un harness no deberia solo resolver la tarea actual; deberia acumular capacidades.

---

## 2. Piezas operativas clave

### 2.1 Arquitectura general

| Componente | Funcion | Analogía nuestra |
|------------|---------|------------------|
| **Automatic Curriculum** | Propone la siguiente tarea segun estado, progreso, tareas completadas/fallidas y objetivo global de explorar | `structurer` / `planner`, pero hoy no son autonomos ni open-ended |
| **Skill Library** | Guarda programas exitosos como skills recuperables por embedding | `commands/`, `agents/*.md`, futura mission case base |
| **Iterative Prompting** | Ejecuta codigo, lee feedback/errores, refina hasta exito o timeout | `implementer -> tests -> reviewer -> reimplement` |
| **Self-Verification** | Critic LLM decide si la tarea se completo y produce critique si falla | `reviewer`, pero mas local y por micro-task |
| **Code as Action Space** | El agente actua escribiendo JavaScript Mineflayer, no low-level controls | Nuestro agente actua editando codigo y ejecutando tools |

Pseudocodigo conceptual:

1. Leer estado del entorno.
2. Curriculum propone siguiente tarea.
3. Recuperar top-k skills relevantes.
4. Generar codigo para la tarea.
5. Ejecutar codigo.
6. Incorporar feedback del entorno, errores y critique.
7. Reintentar hasta 4 rondas.
8. Si self-verification aprueba, guardar skill y marcar tarea completada.
9. Si falla, marcar tarea como demasiado dificil y pedir nueva tarea.

### 2.2 Automatic Curriculum

El curriculum no es una lista fija. GPT-4 propone tareas bottom-up usando:

- inventario, equipo, bloques cercanos, entidades, bioma, tiempo, salud, hambre, posicion;
- tareas completadas y fallidas;
- contexto adicional via self-ask/self-answer con GPT-3.5;
- restricciones fuertes: una sola tarea, alcanzable, verificable, novedosa, no repetir salvo necesidad.

Detalle util: usan **warm-up schedule**. Al principio el prompt solo incluye informacion basica; conforme el agente completa tareas, se incorporan mas señales: entidades, inventario completo, bioma, salud, hambre, tiempo, contexto adicional. Esto evita sobrecargar al agente demasiado pronto.

Lectura para nosotros: es **progressive disclosure aplicada al estado del agente**, no solo a documentacion. Muy relevante.

### 2.3 Skill Library

Cada skill es codigo ejecutable que resuelve una tarea concreta. Se guarda cuando:

1. el codigo se ejecuta;
2. el entorno cambia;
3. self-verification confirma que la tarea se completo.

La skill se indexa por embedding de su descripcion. Para una nueva tarea, Voyager:

- genera una sugerencia general con GPT-3.5;
- combina esa sugerencia con feedback del entorno;
- recupera top-5 skills relevantes;
- pasa esas skills a GPT-4 como contexto para sintetizar una nueva skill.

Resultado importante: evaluan retrieval sobre 309 muestras y reportan `96.5%` top-5 accuracy (`80.2%` top-1). Esto sugiere que una libreria de skills simple, si las descripciones son buenas, puede ser bastante fiable.

### 2.4 Iterative Prompting Mechanism

Voyager usa tres tipos de feedback:

| Feedback | Fuente | Para que sirve |
|----------|--------|----------------|
| **Environment feedback** | chat/logs del entorno: "necesito 2 planks mas" | progreso parcial y causa semantica de fallo |
| **Execution errors** | interpreter/runtime errors | bug fixing de codigo |
| **Self-verification** | GPT-4 critic con estado + task | success/fail + critique accionable |

El loop se corta si:

- el critic confirma exito -> skill se guarda;
- pasan 4 rondas sin exito -> tarea se marca como fallida y curriculum propone otra.

Esto es un detalle de diseño fuerte: **no atascarse eternamente**. El sistema puede volver a la tarea mas tarde cuando tenga mas recursos/skills.

### 2.5 Code as Action Space

Voyager no actua con acciones primitivas tipo teclado/raton. Escribe programas Mineflayer:

- `mineBlock`
- `craftItem`
- `smeltItem`
- `killMob`
- `exploreUntil`
- `getItemFromChest`
- etc.

Esto permite acciones temporally extended, composicionales e interpretables. En terminos de nuestro stack: el agente no deberia solo "hacer pasos"; deberia crear **scripts/tools reutilizables** cuando una rutina aparece mas de una vez.

---

## 3. Resultados principales

### 3.1 Exploracion open-ended

En 160 prompting iterations:

- Voyager descubre `63` items unicos.
- Reportan `3.3x` mas items unicos que baselines.
- ReAct y Reflexion casi no progresan bajo un objetivo open-ended tan abstracto.
- AutoGPT progresa, pero menos, por falta de curriculum adaptativo y skill memory.

### 3.2 Tech tree mastery

| Metodo | Wooden Tool | Stone Tool | Iron Tool | Diamond Tool |
|--------|-------------|------------|-----------|--------------|
| ReAct | N/A `(0/3)` | N/A `(0/3)` | N/A `(0/3)` | N/A `(0/3)` |
| Reflexion | N/A `(0/3)` | N/A `(0/3)` | N/A `(0/3)` | N/A `(0/3)` |
| AutoGPT | `92±72` `(3/3)` | `94±72` `(3/3)` | `135±103` `(3/3)` | N/A `(0/3)` |
| Voyager w/o Skill Library | `7±2` `(3/3)` | `9±4` `(3/3)` | `29±11` `(3/3)` | N/A `(0/3)` |
| **Voyager** | **`6±2` `(3/3)`** | **`11±2` `(3/3)`** | **`21±7` `(3/3)`** | **`102` `(1/3)`** |

Interpretacion: el curriculum explica gran parte del salto inicial; la skill library importa mas conforme las tareas se vuelven composicionales.

### 3.3 Generalizacion zero-shot a mundo nuevo

Resetean inventario y mundo, y prueban tareas no vistas:

| Metodo | Diamond Pickaxe | Golden Sword | Lava Bucket | Compass |
|--------|-----------------|--------------|-------------|---------|
| ReAct | N/A `(0/3)` | N/A `(0/3)` | N/A `(0/3)` | N/A `(0/3)` |
| Reflexion | N/A `(0/3)` | N/A `(0/3)` | N/A `(0/3)` | N/A `(0/3)` |
| AutoGPT | N/A `(0/3)` | N/A `(0/3)` | N/A `(0/3)` | N/A `(0/3)` |
| AutoGPT + Voyager Skill Library | `39` `(1/3)` | `30` `(1/3)` | N/A `(0/3)` | `30` `(2/3)` |
| Voyager w/o Skill Library | `36` `(2/3)` | `30±9` `(3/3)` | `27±9` `(3/3)` | `26±3` `(3/3)` |
| **Voyager** | **`19±3` `(3/3)`** | **`18±7` `(3/3)`** | **`21±5` `(3/3)`** | **`18±2` `(3/3)`** |

Lo mas interesante: la skill library ayuda incluso a AutoGPT. Es decir, la libreria es un asset portable, no solo un componente acoplado a Voyager.

### 3.4 Ablations

Hallazgos principales:

- Reemplazar el curriculum automatico por random curriculum reduce discovered item count en `93%`.
- Quitar skill library causa plateau en etapas tardias.
- Quitar self-verification reduce discovered item count en `73%`.
- GPT-4 para code generation obtiene `5.7x` mas items unicos que GPT-3.5.
- Environment feedback, execution errors y self-verification son complementarios; quitar cualquiera degrada.

### 3.5 Limitaciones

- **Coste:** GPT-4 era 15x mas caro que GPT-3.5; el sistema depende de su salto en coding.
- **Inaccuracies:** el agente aun se atasca y genera skills incorrectas.
- **Self-verification falla:** a veces no reconoce senales indirectas de exito.
- **Hallucinated tasks:** curriculum propone objetos inexistentes como copper sword.
- **Hallucinated APIs:** GPT-4 llama funciones ausentes o usa conceptos invalidos del juego.
- **Sin vision directa:** trabaja con estado textual; tareas de construccion visual requieren humano/multimodal feedback.

---

## 4. Qué adoptamos en HERO y cómo está implementado

Voyager propone acumular habilidades verificadas y recuperarlas en tareas futuras. HERO implementa la skill library y el retrieval, manteniendo el sistema acotado al objetivo del usuario.

### Skill library post-misión (solo skills verificadas)
- **Del paper:** guardar una skill solo cuando se verificó en entorno real; las skills son código reutilizable.
- **En HERO:** `src/harness/skill_library.py` persiste skills generadas (directorio de generated-skills) con estado `verified` y las expone al implementer vía `retrieved-skills.md`. Solo entran patrones que pasaron review/tests.

### Retrieval top-k de skills y casos
- **Del paper:** recuperar las skills relevantes antes de actuar.
- **En HERO:** el retrieval usa solapamiento de tokens TF-IDF (no embeddings) en `src/harness/skill_library.py` para skills y `src/harness/case_base.py` para misiones aprobadas (`retrieved-cases.md`, `mission-cases.jsonl`).

### Self-verification antes del reviewer final
- **Del paper:** la self-verification es el feedback type más importante (ablation −73%).
- **En HERO:** el implementer ejecuta `## Self-Verification` con sub-checks locales antes de cerrar (`agents/implementer.md`, validado por gate en `src/core/gate.py`), reduciendo basura antes del reviewer.

### Memoria de completadas/fallidas y modos de fallo
- **Del paper:** memoria de tareas completadas/fallidas que informa el progreso.
- **En HERO:** `status.md` marca STATUS (DONE/BLOCKED) validado por gate (`src/core/gate.py`); la memoria de proyecto registra "Recurring Failure Modes" (`PROJECT_MEMORY.md` vía `src/harness/project_memory.py`).

## 5. No adoptado (y por qué)

- **Automatic curriculum adaptativo / open-ended:** el `structurer`/`planner` descomponen la misión, pero no existe un curriculum vivo que invente subtareas; HERO es opt-in y acotado al objetivo del usuario (sin scope creep).
- **Regla formal "4 intentos y aparcar":** hay reintentos y HITL, pero no una regla de abandono temporal con re-priorización automática.
- **Vector DB para retrieval:** se usa similitud por tokens TF-IDF deliberadamente; no se introduce base vectorial hasta tener corpus suficiente.

---

## 6. Sintesis con papers previos

- **Paper 04 (Code as Agent Harness):** Voyager es ejemplo fuerte de agent-initiated code artifacts: las skills son codigo ejecutable que el agente crea para si mismo.
- **Paper 05 (Continual Harness):** ambos tratan lifelong learning; Voyager acumula skills, Continual Harness edita el harness. Son complementarios.
- **Paper 06 (DSPy):** DSPy optimiza prompts/pipelines; Voyager construye una libreria de programas ejecutables. DSPy compila llamadas; Voyager acumula acciones.
- **Paper 07 (Vesper):** ambos usan codigo como unidad de mejora y memoria. Vesper guarda programas en DB evolutiva; Voyager guarda skills verificadas por task.
- **Paper 08 (Inference-Time Alignment):** automatic curriculum es una estrategia de granularidad/capability alignment; self-verification es guidance evidence-anchored.
- **Paper 09 (Reflexion):** Voyager mejora Reflexion al sumar self-verification explicita, environment feedback y skill persistence. Reflexion recuerda; Voyager aprende habilidades.
- **Paper 10 (TextGrad):** iterative prompting de Voyager se puede reinterpretar como loss/gradient/update sobre una skill de codigo, con self-verification como loss.
