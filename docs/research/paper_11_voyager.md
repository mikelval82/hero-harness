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

## 4. Mapeo a nuestro harness

| Voyager | Nuestro harness | Diagnostico |
|---------|-----------------|-------------|
| Automatic curriculum | `structurer`, `planner`, `tasks.json` | Tenemos descomposicion, pero no curriculum adaptativo vivo |
| Completed/failed task memory | `status.md`, `audit.md`, context hot/cold | Existe, pero no se usa para proponer subtareas nuevas |
| Skill library | `commands/`, skills de Codex, futura case base | Tenemos skills estaticas; no generamos skills automaticamente tras exito |
| Code skills | Scripts/tests/helpers que el agente podria crear | Aun no hay politica clara para agent-initiated reusable tools |
| Skill retrieval | `context-cold.md`, code graph, rg | Retrieval semantico de casos/skills no existe |
| Iterative prompting | reviewer -> reimplement loop | Existe, pero a nivel tarea; Voyager lo hace a nivel micro-skill |
| Self-verification | `reviewer` | Reviewer es fuerte pero tardio; falta critic local por subtask |
| Environment feedback | test output, tool output, runtime errors, git diff | Tenemos feedback, pero no siempre estructurado como progreso parcial |
| Max 4 rounds then move on | retries / HITL | No tenemos una regla formal de abandono temporal y reintento posterior |
| Warm-up schedule | divulgacion progresiva | Lo aplicamos a docs, no a estado/artefactos de mision |

**Posicion:** Voyager es un blueprint para convertir nuestro harness de "pipeline que resuelve tareas" a "sistema que acumula habilidades". Pero no debe copiarse literalmente: nuestro dominio no es open-ended Minecraft, sino engineering tasks con user intent, repo constraints y review humano.

---

## 5. Aplicabilidad — Harness

| Idea Voyager | Coste | Beneficio | Impacto | Novedad |
|--------------|-------|-----------|---------|---------|
| **Skill library post-mision**: guardar patrones/commands/scripts de misiones aprobadas | Medio | Alto | Alto | Media |
| **Retrieval top-k de skills/casos** antes de implementar | Medio | Alto si hay corpus | Alto | Media |
| **Self-verification local por subtask** antes del reviewer final | Bajo-medio | Alto | Alto | Baja |
| **Regla "4 intentos y aparcar"** para subtareas bloqueadas | Bajo | Medio | Medio | Baja |
| **Completed/failed task memory** en `tasks.json` | Bajo | Medio | Medio | Baja |
| **Warm-up de contexto** segun progreso de tarea | Medio | Medio | Medio | Media |
| **Automatic curriculum para misiones grandes** | Medio-alto | Medio | Medio | Media |
| **Generacion automatica de commands/skills** | Alto | Alto a largo plazo | Alto | Alta |

### 5.1 Skill library como siguiente evolucion natural

La leccion mas transferible es:

> Solo guardes una skill cuando fue verificada en entorno real.

Para nuestro harness, eso significa:

- no guardar "ideas";
- no guardar prompts bonitos;
- guardar rutinas que pasaron tests/review en una mision real.

Ejemplos de skills que podria aprender el harness:

- "como anadir un phase al runner sin romper tests";
- "como escribir un reviewer que no edita codigo";
- "como crear un command nuevo siguiendo formato";
- "como testear path policy en Windows";
- "como extender `MissionRunner` sin tocar artefactos del proyecto target".

Cada skill deberia tener:

```text
Description:
When to use:
Preconditions:
Files touched:
Commands/tests used:
Failure modes:
Verified by:
```

### 5.2 Self-verification antes del reviewer final

Voyager demuestra que self-verification no es un detalle: es el feedback type mas importante. En nuestro harness, el reviewer final es caro y tardio. Podriamos anadir checks locales por subtask:

- "la feature compila";
- "el test nuevo falla antes y pasa despues";
- "no se escribieron artefactos del harness en proyecto target";
- "el cambio respeta zero footprint";
- "la tarea del plan realmente quedo hecha".

Esto no sustituye al reviewer. Reduce basura antes de llegar al reviewer.

### 5.3 Automatic curriculum sin caer en scope creep

No necesitamos open-ended exploration para tareas de usuario. Pero si puede servir en:

- misiones grandes;
- benchmark generation;
- discovery de refactors;
- backlog interno de mejora del harness.

La version segura seria: **curriculum bounded**, no open-ended. El usuario fija objetivo y constraints; el curriculum solo propone la siguiente subtarea alcanzable dentro de ese objetivo.

### 5.4 Donde NO copiar Voyager

- No dejar que el harness invente objetivos de producto sin usuario.
- No guardar skills sin verificacion fuerte.
- No usar LLM self-verification como unico gate.
- No meter vector DB antes de tener corpus suficiente.
- No asumir que Minecraft transfer = software engineering transfer.
- No usar "open-ended" como excusa para scope creep.

---

## 6. Aplicabilidad — Paper / benchmark

| Uso | Valor |
|-----|-------|
| **Related work** | Alto. Es referencia clave de lifelong LLM agents con skill library ejecutable. |
| **Soporte para "skills as reusable code"** | Muy alto. Encaja con paper 04 y nuestra posible case base. |
| **Baseline directo** | Bajo. Dominio embodied/open-ended, no SWE benchmark. |
| **Inspiracion para benchmark secundario** | Medio. Podriamos medir aprendizaje cross-task por reuse de skills. |
| **Cita para self-verification** | Alto. Ablation `-73%` es municion fuerte. |
| **Cita para automatic curriculum** | Alto en framing; cuidado con dominio. |

### Implicacion para contenders

Voyager no deberia entrar como contender en nuestro MVP. Es otro regimen:

- entorno open-ended;
- tareas generadas por el agente;
- skill accumulation;
- Mineflayer APIs;
- feedback textual del mundo.

Pero si sugiere un **experimento post-MVP**:

1. Correr varias tareas relacionadas con el harness.
2. Guardar skills verificadas tras cada tarea.
3. Medir si el contender con skill retrieval resuelve tareas posteriores con menos tokens/retries.

Ese experimento testaria algo distinto a H1-H5: **lifelong harness learning**.

---

## 7. Riesgo / beneficio / impacto / novedad

### 7.1 Como aporte al harness

El mayor valor practico es la skill library. Nuestro `context-cold.md` comprime hallazgos, pero no convierte esos hallazgos en programas/skills invocables. Voyager muestra que la diferencia entre "memoria" y "habilidad" importa: memoria describe; skill ejecuta.

La segunda idea mas fuerte es el curriculum adaptativo. En misiones grandes, el plan inicial puede quedar obsoleto tras nuevos hallazgos. Voyager propone una regla sana: elegir la proxima tarea segun estado actual, completadas/fallidas y frontera de capacidad.

### 7.2 Como aporte al paper

Voyager no compite con nuestro harness, pero refuerza una tesis transversal: los agentes fuertes no son solo prompts largos; son sistemas con **memory, reusable tools, curriculum, verification y execution feedback**. Es un paper excelente para la seccion de related work sobre skill accumulation y code-as-action.

### 7.3 Riesgos

- **Skill bloat:** una libreria de skills sin curacion se degrada rapido.
- **Retrieval poisoning:** recuperar una skill parecida pero equivocada puede inducir errores sutiles.
- **Verifier drift:** self-verification puede aprobar falsos positivos.
- **Autonomy creep:** automatic curriculum puede inventar trabajo fuera del objetivo del usuario.
- **Coste:** skill generation + verification + retrieval añade overhead.
- **Portabilidad:** skills de Minecraft son funciones limpias; skills de software engineering dependen de repos, convenciones y contexto.

---

## 8. Decisiones recomendadas

### Para el harness

1. **Diseñar una skill library post-mision**, no runtime al principio. Guardar solo patterns verificados por tests/reviewer.
2. **Crear formato de skill verificable**: description, preconditions, files, commands, failure modes, verification.
3. **Anadir self-verification local** antes del reviewer final: checklist por task/subtask.
4. **Formalizar completed/failed tasks** dentro de `tasks.json` o `status.md`, con razon de fallo.
5. **Usar curriculum bounded** para misiones grandes: proxima subtarea segun estado real, no segun plan inicial congelado.
6. **No construir vector DB todavia**. Primero acumular 20-30 skills/casos; luego evaluar retrieval.
7. **Adoptar regla de abandono temporal**: si una subtarea falla N veces, aparcarla, desbloquear prerequisitos y volver despues.

### Para el paper

1. **Citar Voyager** en related work de lifelong/open-ended agents y skill libraries.
2. **Usarlo para justificar skill accumulation** como future work o experimento post-MVP.
3. **No incluirlo como contender** en el benchmark principal.
4. **Citar ablations clave**: self-verification `-73%`, random curriculum `-93%`, GPT-4 vs GPT-3.5 `5.7x`.
5. **Diferenciar claramente:** Voyager = embodied lifelong learning; nuestro paper = metodologia de orquestacion para software engineering bajo tareas dadas por usuario.

---

## 9. Veredicto franco

Voyager es un paper **excelente** y muy bien diseñado. No por "Minecraft", sino porque une tres cosas que muchos agentes tratan por separado:

1. decidir que aprender despues;
2. verificar si realmente se aprendio;
3. guardar lo aprendido como codigo reutilizable.

Para nuestro trabajo, su mensaje central es incomodo y util: un harness que solo compacta contexto no aprende skills. Aprende cuando convierte ejecuciones exitosas en unidades reutilizables, verificadas y recuperables.

**Accion concreta sugerida:**

1. Anotar `skill library post-mision` como feature post-MVP.
2. Reforzar `reviewer` / `implementer` con self-verification local por subtask.
3. Anadir al paper un eje futuro: "cross-task skill reuse".
4. No distraerse con open-ended autonomy todavia. Nuestro producto debe seguir siendo opt-in y user-bounded.

---

## 10. Sintesis con papers previos

- **Paper 04 (Code as Agent Harness):** Voyager es ejemplo fuerte de agent-initiated code artifacts: las skills son codigo ejecutable que el agente crea para si mismo.
- **Paper 05 (Continual Harness):** ambos tratan lifelong learning; Voyager acumula skills, Continual Harness edita el harness. Son complementarios.
- **Paper 06 (DSPy):** DSPy optimiza prompts/pipelines; Voyager construye una libreria de programas ejecutables. DSPy compila llamadas; Voyager acumula acciones.
- **Paper 07 (Vesper):** ambos usan codigo como unidad de mejora y memoria. Vesper guarda programas en DB evolutiva; Voyager guarda skills verificadas por task.
- **Paper 08 (Inference-Time Alignment):** automatic curriculum es una estrategia de granularidad/capability alignment; self-verification es guidance evidence-anchored.
- **Paper 09 (Reflexion):** Voyager mejora Reflexion al sumar self-verification explicita, environment feedback y skill persistence. Reflexion recuerda; Voyager aprende habilidades.
- **Paper 10 (TextGrad):** iterative prompting de Voyager se puede reinterpretar como loss/gradient/update sobre una skill de codigo, con self-verification como loss.
