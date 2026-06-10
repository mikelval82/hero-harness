# Harness - mapas de arquitectura y flujo

Este documento es un mapa de lectura progresiva. Empieza por los diagramas de
alto nivel y baja solo cuando necesites entender un subsistema concreto.

Fuentes vivas principales:

- Entry point: `src/cli.py`.
- Orquestacion: `src/mission/runner.py`, `src/mission/task_executor.py`.
- Configuracion de fases y modos: `src/core/context.py`.
- Routing de modelos: `src/core/model_policy.py`.
- Runtime agentico: `src/mission/phase_runner.py`, `src/agent/loop.py`, `src/agent/tools.py`.
- Estado y memoria del harness: `src/harness/*`.

---

## Nivel 0 - Modelo mental

El harness no es un unico agente. Es un sistema de control alrededor de un LLM:
prepara contexto, decide rutas, ejecuta fases con herramientas, valida artefactos,
recupera fallos, registra trazas y conserva aprendizaje reutilizable.

```mermaid
flowchart LR
    USER([Usuario]) --> CLI[src/cli.py]
    CLI --> CTX[MissionContext]

    CTX --> ORCH[MissionRunner]
    ORCH --> PHASES[Fases agenticas]
    ORCH --> TASKS[Loop de tareas]
    ORCH --> FINAL[Reporte y cierre]

    PHASES --> LLM[Anthropic Messages API]
    PHASES --> TOOLS[Read / Write / Edit / Bash / search]
    TASKS --> TARGET[Proyecto target]

    ORCH --> HARNESS[$CLAUDE_HARNESS]
    HARNESS --> ARTIFACTS[Artefactos de mision]
    HARNESS --> TELEMETRY[Telemetry]
    HARNESS --> MEMORY[Memoria / cases / skills]

    FINAL --> GIT[Git opcional]
    FINAL --> NOTIFY[Telegram / stdout]
```

---

## Nivel 1 - Etapas de una mision

Todas las misiones se organizan como `setup -> init -> task loop -> finalize`.
El modo (`--mode`) decide que fases entran en cada bloque.

```mermaid
flowchart TD
    START([Inicio]) --> PARSE[Parse args]
    PARSE --> SETUP[setup_harness]
    SETUP --> STAGE[Stage memory, cases, skills]
    STAGE --> CLIENT[Crear cliente Anthropic]
    CLIENT --> RUNNER[create_runner]

    RUNNER --> RESUME{resume con tasks.json?}
    RESUME -->|si| LOAD[Leer tasks.json]
    RESUME -->|no| INIT[Init pipeline por mode]

    INIT --> EXPLORE{mode == explore?}
    EXPLORE -->|si| FINALIZE[Finalize]
    EXPLORE -->|no| LOAD

    LOAD --> LIMIT{tasks > max_tasks?}
    LIMIT -->|si| CONSOLIDATE[Consolidate tasks]
    LIMIT -->|no| LOOP[Task loop]
    CONSOLIDATE --> LOOP

    LOOP --> FINALIZE
    FINALIZE --> PRECOMMIT{finalize incluye merge?}
    PRECOMMIT -->|si| FINAL_COMMIT[final_commit]
    PRECOMMIT -->|no| REPORT[Generate report]
    FINAL_COMMIT --> REPORT
    REPORT --> SYNC[Sync memory, cases, skills]
    SYNC --> MERGE{finalize incluye merge?}
    MERGE -->|si| GIT[merge_to_develop]
    MERGE -->|no| END([Fin])
    GIT --> END
```

### Modos de mision

| Mode | Init pipeline | Task pipeline | Finalize | Uso |
|---|---|---|---|---|
| `full` | `research -> compact -> grill? -> structure` | por complejidad S/M/L | `report + merge` | Ruta completa por defecto |
| `focused` | `research -> structure` | por complejidad S/M/L | `report + merge` | Menos conversacion inicial |
| `hotfix` | ninguno | por complejidad S/M/L | `report + merge` | Reusar `tasks.json` existente |
| `explore` | `research` | ninguno | `report` | Solo investigacion |
| `spec` | `research -> grill? -> structure` | `spec` | `report` | Partial harness spec-only |
| `spec-plan` | `research -> grill? -> structure` | `spec -> plan` | `report` | Partial harness spec+plan |

`grill?` se omite con `--no-grill`.
`spec-plan` es el nombre canonico del partial harness que llega hasta `plan.md`;
no existe modo `plan` ni flag `--plan-only`.

---

## Nivel 2 - Pipeline por tarea

`TaskExecutor` borra artefactos stale, reconstruye el grafo de codigo, elige
pipeline, ejecuta fases, registra telemetry y marca estado en `tasks.json`.

```mermaid
flowchart TD
    TASK[Siguiente tarea] --> DONE{ya completed?}
    DONE -->|si| NEXT[Siguiente]
    DONE -->|no| CLEAN[Limpiar artefactos de tarea]
    CLEAN --> GRAPH[build_code_graph]
    GRAPH --> PARTIAL{mode parcial?}

    PARTIAL -->|spec| SPEC_ONLY[SPEC]
    PARTIAL -->|spec-plan| SPEC_PLAN[SPEC -> PLAN]
    PARTIAL -->|no| COMPLEXITY{complexity}

    COMPLEXITY -->|S| SIMPLE[IMPLEMENT]
    COMPLEXITY -->|M| STANDARD[SPEC -> PLAN -> IMPLEMENT -> REVIEW]
    COMPLEXITY -->|L| LARGE[SPEC -> PLAN -> IMPLEMENT_BURSTS -> REVIEW]

    SPEC_ONLY --> PARTIAL_DONE[completed + compact]
    SPEC_PLAN --> PARTIAL_DONE
    SIMPLE --> NO_REVIEW[auto approve sin REVIEW]
    STANDARD --> REVIEW_FLOW[review / HITL]
    LARGE --> REVIEW_FLOW

    NO_REVIEW --> STAGE[stage_task_files]
    REVIEW_FLOW --> OUTCOME{approved?}
    OUTCOME -->|si| STAGE
    OUTCOME -->|no| FAIL[task failed]
    STAGE --> MARK[task completed]
    MARK --> COMPACT[compact_context]
    FAIL --> NEXT
    PARTIAL_DONE --> NEXT
    COMPACT --> NEXT
```

### Routing S/M/L

| Complexity | Pipeline | Coste | Riesgo cubierto |
|---|---|---:|---|
| `S` | `implement` | bajo | cambios pequenos y acotados |
| `M` | `spec -> plan -> implement -> review` | medio | flujo normal con reviewer |
| `L` | `spec -> plan -> implement_bursts -> review` | alto | tareas amplias o con mucho riesgo |

Los modos parciales ignoran S/M/L: `spec` fuerza `SPEC`; `spec-plan` fuerza
`SPEC -> PLAN`.

---

## Nivel 3 - Ejecucion de una fase

Cada fase es un `PhaseConfig` en `PHASE_REGISTRY`: agente, prompt, gate,
herramientas, includes, timeout y `max_turns`.

```mermaid
flowchart TD
    CONFIG[PhaseConfig] --> INCLUDES[Resolver includes desde harness]
    INCLUDES --> PROMPT[render_prompt]
    CONFIG --> AGENT[load_agent_system si aplica]
    PROMPT --> MODEL[select_model_for_phase]
    AGENT --> MODEL
    MODEL --> RUN[agent_loop.run_phase]

    RUN --> API[Anthropic Messages API]
    API --> TOOL_USE{tool_use?}
    TOOL_USE -->|si| EXEC[ToolExecutor]
    EXEC --> TARGET[project_dir]
    EXEC --> HARNESS[harness_dir]
    EXEC --> API
    TOOL_USE -->|no| RESULT[PhaseResult]

    RESULT --> METRIC[_metrics.jsonl + _telemetry.jsonl]
    RESULT --> GATE{gate file?}
    GATE -->|si| CHECK[check_gate]
    GATE -->|no| OK[phase ok]
    CHECK -->|pass| OK
    CHECK -->|fail| BLOCK[blocked.reason]
```

### Capas del runtime agentico

| Capa | Modulo | Responsabilidad |
|---|---|---|
| Prompting | `src/harness/prompt_renderer.py` | Expande templates, includes y footer de workspace |
| Model routing | `src/core/model_policy.py` | Elige modelo por fase, complejidad y overrides de entorno |
| Phase control | `src/mission/phase_runner.py` | Ejecuta fase, valida gate, captura errores |
| Agent loop | `src/agent/loop.py` | Conversacion con Anthropic, retries, timeout, tokens |
| Tool dispatch | `src/agent/tools.py` | Enruta herramientas al handler real |
| Tool schema | `src/agent/tool_schema.py` | Define herramientas disponibles por nombre |
| File/search/bash tools | `src/agent/*_tools.py` | Operaciones sobre proyecto y harness |

### Routing de modelos

El harness no usa un unico modelo para todo. Antes de cada llamada a Anthropic,
`select_model_for_phase()` decide un tier:

| Tier | Modelo por defecto | Uso |
|---|---|---|
| `cheap` | `claude-haiku-4-5` | compactacion, consolidacion, reportes |
| `default` | `claude-sonnet-4-6` | research normal, structure, spec, plan, implement |
| `deep` | `claude-opus-4-7` | grill, review, reimplement, tareas `L`, explore research |

Overrides de entorno:

| Variable | Efecto |
|---|---|
| `CLAUDE_HARNESS_MODEL_CHEAP` | cambia el modelo del tier cheap |
| `CLAUDE_HARNESS_MODEL_DEFAULT` | cambia el modelo del tier default |
| `CLAUDE_HARNESS_MODEL_DEEP` | cambia el modelo del tier deep |
| `CLAUDE_HARNESS_MODEL_FORCE` | fuerza un unico modelo para todas las fases |

`PhaseResult`, `_metrics.jsonl` y `_telemetry.jsonl` registran el modelo usado
por fase. La telemetria calcula `estimated_usd` cuando el modelo esta en la
tabla local de precios; si no, marca `missing_component=model_pricing`.

---

## Nivel 4 - Artefactos y memoria

`$CLAUDE_HARNESS` es el workspace efimero de la mision. El proyecto target solo
recibe cambios de codigo cuando una tarea se stagea/commitea.

```mermaid
flowchart LR
    subgraph PERSIST["Persistente por proyecto"]
        PMEM[PROJECT_MEMORY.md]
        CASES[cases.jsonl]
        SKILLS[skills.jsonl + skills/*.md]
    end

    subgraph HARNESS["$CLAUDE_HARNESS"]
        BRAIN[brainstorm.md]
        BRIEF[brief.md]
        TASKS[tasks.json]
        SPEC[spec.md]
        PLAN[plan.md]
        DEC[decisions.md]
        STATUS[status.md]
        AUDIT[audit.md]
        HOT[context-hot.md]
        COLD[context-cold.md]
        GRAPH[code_graph.json]
        TEL[_telemetry.jsonl]
        REPORT[mission-report.md]
        STAGED_MEM[project-memory.md]
        RET_CASES[retrieved-cases.md]
        RET_SKILLS[retrieved-skills.md]
        GEN_SKILLS[generated-skills/*.md]
    end

    PMEM --> STAGED_MEM
    CASES --> RET_CASES
    SKILLS --> RET_SKILLS

    STAGED_MEM --> PHASES[Fases]
    RET_CASES --> PHASES
    RET_SKILLS --> PHASES
    PHASES --> BRAIN
    PHASES --> TASKS
    PHASES --> SPEC
    PHASES --> PLAN
    PHASES --> STATUS
    PHASES --> AUDIT
    PHASES --> HOT
    PHASES --> TEL

    HOT --> COMPACT[compact_context]
    COMPACT --> COLD
    REPORT --> PMEM
    GEN_SKILLS --> SKILLS
    REPORT --> CASES
```

### Artefactos principales

| Artefacto | Ciclo de vida | Productor |
|---|---|---|
| `brainstorm.md` | por mision | researcher |
| `brief.md` | opcional, por mision | griller |
| `tasks.json` | fuente de verdad de tareas | structurer + task updater |
| `spec.md` | por tarea, overwrite | specifier |
| `plan.md` | por tarea, overwrite | planner |
| `decisions.md` | por tarea, overwrite o placeholder | planner / runner |
| `status.md` | por tarea | implementer |
| `audit.md` | por tarea | reviewer |
| `context-hot.md` | capa activa | agentes |
| `context-cold.md` | capa historica compactada | compact phase |
| `_telemetry.jsonl` | append-only | runner / phase logger / HITL |
| `mission-report.md` | final | report phase |

---

## Nivel 5 - Review, HITL y recuperacion

El reviewer no edita codigo. Produce `audit.md`; `HitlReviewer` decide si se
stagea, se reimplementa, se pide input humano o se marca fallo.

```mermaid
flowchart TD
    IMPLEMENT[Implement / bursts] --> REVIEW[Review]
    REVIEW --> AUDIT[audit.md]
    AUDIT --> VERDICT{verdict}

    VERDICT -->|APPROVED| GATE{gate auto/manual}
    VERDICT -->|MINOR_CHANGES| FAST[REIMPLEMENT fast-path]
    VERDICT -->|CHANGES_REQUESTED| HITL[HITL loop]

    FAST --> STAGE[stage + complete]

    GATE -->|auto| STAGE
    GATE -->|manual| WAIT[esperar approve/reject]
    WAIT -->|approve| STAGE
    WAIT -->|reject| FAIL[task failed]

    HITL --> CMD{comando}
    CMD -->|retry feedback| REIMPL[REIMPLEMENT]
    REIMPL --> REVIEW2[REVIEW otra vez]
    REVIEW2 --> VERDICT
    CMD -->|skip| FAIL
    CMD -->|approve| STAGE
    CMD -->|abort| ABORT[mission abort]

    STAGE --> COMPACT[compact_context]
    FAIL --> NEXT[Siguiente tarea]
    COMPACT --> NEXT
```

Telemetry registra `waiting_approval`, `approve`, `reject`, `retry`, `skip`,
`force_approve`, `abort` y `auto_reimplement`.

---

## Nivel 6 - Aprendizaje post-mision

El harness conserva aprendizaje fuera del workspace efimero, pero no aplica
parches automaticamente a prompts/agentes.

```mermaid
flowchart TD
    REPORT[mission-report.md] --> MEMORY{learning durable?}
    REPORT --> CASE{mision aprobada?}
    REPORT --> SKILL{skill verificada?}

    MEMORY -->|si| PROJECT_MEMORY[$HOME/.harness-memory/.../PROJECT_MEMORY.md]
    CASE -->|si| CASE_BASE[$HOME/.harness-memory/.../cases.jsonl]
    SKILL -->|si| SKILL_LIB[$HOME/.harness-memory/.../skills/*.md]

    AUDIT[audit.md] --> REFINER[refiner offline]
    TELEMETRY[_telemetry.jsonl] --> REFINER
    CASE_BASE --> REFINER
    REFINER --> PROPOSAL[refiner-proposal.md]
    PROPOSAL --> HUMAN[aprobacion humana requerida]
```

| Subsistema | Entrada | Salida | Nota |
|---|---|---|---|
| Project memory | reporte y artefactos | `PROJECT_MEMORY.md` | Convenciones duraderas del repo |
| Mission case base | misiones aprobadas | `cases.jsonl` | Retrieval lexical top-k |
| Skill library | skills `status: verified` | `skills/*.md` + index | Procedimientos reutilizables |
| Refiner | fallos recurrentes | `refiner-proposal.md` | `auto_apply: false` |

---

## Nivel 7 - Mapa de modulos

```mermaid
flowchart LR
    CLI[src/cli.py] --> CORE[src/core]
    CLI --> MISSION[src/mission]
    MISSION --> HARNESS[src/harness]
    MISSION --> AGENT[src/agent]
    MISSION --> ANALYSIS[src/analysis]
    MISSION --> INTEGRATIONS[src/integrations]

    CORE --> CONTEXT[context / state / gate / git]
    MISSION --> RUNNERS[runner / task_executor / phase_runner / hitl / burst_runner]
    HARNESS --> STORAGE[tasks / telemetry / memory / cases / skills / prompt_renderer]
    AGENT --> RUNTIME[loop / tools / schemas / file-search-bash]
    ANALYSIS --> GRAPH[code_graph / sqlite_graph]
    INTEGRATIONS --> IO[telegram / notifier]
```

### Responsabilidades por carpeta

| Carpeta | Responsabilidad |
|---|---|
| `src/core` | Tipos y servicios base: contexto, gates, estado, git, notificacion |
| `src/mission` | Orquestacion de mision, tarea, fases, HITL y reporting |
| `src/harness` | Artefactos, memoria persistente, telemetry, prompt rendering |
| `src/agent` | Loop LLM y herramientas ejecutables |
| `src/analysis` | Grafo de codigo y vistas SQLite |
| `src/integrations` | Telegram, notificaciones y comandos externos |
| `agents/` | Instrucciones de sistema por rol |
| `prompts/` | Templates de fase |
| `commands/` | Comandos manuales fuera del pipeline automatico |

---

## Invariantes utiles

- `tasks.json` es la fuente de verdad de tareas y estados.
- El reviewer es read-only sobre codigo; solo escribe `audit.md`.
- Los modos parciales (`spec`, `spec-plan`) no implementan, no revisan, no stagean y no mergean.
- `full`, `focused` y `hotfix` pueden hacer `final_commit` y `merge_to_develop`.
- `explore` no entra en task loop.
- `PhaseRunner` valida gates despues de cada fase con gate file.
- `_telemetry.jsonl` registra fases, coste/token, tareas e intervenciones HITL.
- `project-memory.md`, `retrieved-cases.md` y `retrieved-skills.md` se inyectan en fases agenticas.
- `generated-skills/` solo promociona skills con `status: verified`.
- El refiner propone cambios offline y requiere aprobacion humana; no modifica prompts/agentes/codigo por si mismo.
