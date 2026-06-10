# Paper 03 — AI Harness Engineering: A Runtime Substrate for Foundation-Model Software Agents

**Autores:** Hailin Zhong (HKBU), Shengxin Zhu (BNU Zhuhai)
**arXiv:** 2605.13357v1, mayo 2026
**Tipo:** Position paper + framework + ilustración (1 tarea controlada, no estudio empírico)
**Fichero:** `papers/ai harness engineering - a runtime substrate for foundation model software agents.pdf`

---

## 1. Tesis del paper en una frase

La capacidad de ingeniería de software autónoma **no** es una propiedad del modelo: es propiedad emergente del sistema **modelo–harness–entorno**. El paper define formalmente qué es un harness (11 componentes, 5 principios), propone una escalera **H0–H3** de ablación controlada para separar empíricamente la contribución del harness vs. la del modelo, y un protocolo de evaluación basado en **trazas** que produce *episode packages* auditables en lugar de un mero pass/fail.

**Este paper es prácticamente el manifiesto teórico de lo que nosotros estamos construyendo.** Es el más directamente relevante de toda la colección.

---

## 2. Las piezas operativas del paper

### 2.1 Ecuación del sistema

$$
C_{\text{system}} = F(C_{\text{model}}, C_{\text{harness}}, C_{\text{environment}}, T)
$$

El "autonomy gap" se define como la diferencia entre la capacidad local de codificación del modelo y la capacidad del sistema completo para completar tareas sin ayuda humana en tiempo de ejecución.

### 2.2 Once componentes del harness

| Componente | Contrato runtime | Fallo si falta | Evidencia que produce |
|------------|------------------|----------------|------------------------|
| Task interface | Presentar objetivo, requisitos, criterios de éxito | Goal underspecified | Task record |
| Context manager | Seleccionar y exponer contenido relevante | Wrong-file inspection | Context trace |
| Tool registry | Declarar tools disponibles | Llamadas fallidas | Tool trace |
| Project memory | Conocimiento legible del proyecto (architecture, testing, known failures) | Redescubrimiento, fix en capa errónea | Memory references |
| Task state | Hipótesis, ficheros inspeccionados, próximos pasos | Drift, trabajo repetido | Task-state file |
| Observability | Logs, trazas, outputs | Unverifiable success | Observation log |
| Failure attribution | Separar observación / esperado / diagnóstico | Patching aleatorio post-fallo | Attribution log |
| Verification protocol | Mapear requisitos a evidencia determinista | Falsa confianza | Verification trace |
| Permission boundary | Restringir acciones de riesgo | Episodios inseguros | Permission record |
| Entropy auditor | Detectar carga de mantenimiento introducida | Docs obsoletas, residuos | Entropy audit |
| Intervention logger | Registrar ayuda humana y su evitabilidad | Andamiaje humano invisible | Intervention log |

### 2.3 Cinco principios de diseño

- **P1 Explicit runtime resources** — recursos críticos nombrados, no implícitos.
- **P2 Traceable mediation** — todo lo que el agente hace queda registrado.
- **P3 Requirement-level verification** — completion atado a evidencia, no a aserción NL.
- **P4 Attribution before recovery** — diagnóstico clasificado antes de volver a editar.
- **P5 Maintenance & entropy awareness** — carga de mantenimiento medida, no externa.

### 2.4 Escalera H0–H3

| Nivel | Añade |
|-------|-------|
| H0 | Sólo task + repositorio. Baseline. |
| H1 | + tool registry, test-command registry, tool-usage protocol |
| H2 | + project memory (AGENT_GUIDE, ARCHITECTURE, TESTING, KNOWN_FAILURES), task state, context-selection protocol |
| H3 | + deterministic check registry, bug-reproduction protocol, failure-attribution protocol, verification protocol, verification report template |

Visibilidad monotónica creciente. Mismo modelo, mismo repo, misma tarea entre niveles.

### 2.5 Taxonomía de fallos (8)

`Fcontext`, `Ftool`, `Ffeedback`, `Fverify`, `Frecovery`, `Fentropy`, `Fmodel`, `Funknown`.

### 2.6 Cinco outcomes finales

- `autonomous_verified_success` — éxito + evidencia + sin intervención humana.
- `assisted_verified_success` — éxito pero progreso dependió de ayuda humana.
- `unverified_success` — parche correcto pero sin evidencia bajo protocolo.
- `failed`
- `unsafe_invalid` — tests debilitados, edits destructivos, bypass.

Separa **comportamiento** de **calidad de evidencia** — clave.

### 2.7 Ocho trazas y métrica estrella

Trazas JSONL: action, tool, context, verification, failure-attribution, intervention, entropy, outcome.

Métrica más relevante para nosotros: **M-HIR (Missing-Harness Human Intervention Rate)** — proporción de intervenciones humanas que indican un componente faltante en el harness. Un harness bueno baja M-HIR.

---

## 3. Qué adoptamos en HERO y cómo está implementado

Este es el paper de referencia: su taxonomía de 11 componentes de un harness está implementada casi al completo en HERO.

| Componente del paper | Implementación en HERO | Fichero(s) |
|----------------------|------------------------|------------|
| Task interface | `brief.md` (griller) + `spec.md` (specifier) con criterios EARS | `agents/griller.md`, `agents/specifier.md` |
| Context manager | grafo de código (tree-sitter) + pizarra `context-hot.md` / `context-cold.md` | `src/analysis/`, `src/mission/burst_runner.py` |
| Tool registry | herramientas acotadas por fase (`DEFAULT`/`IMPL`/`REVIEW`) | `src/core/context.py` |
| Project memory | `PROJECT_MEMORY.md` **por proyecto** en `~/.harness-memory/{project_key}/` | `src/harness/project_memory.py` |
| Task state | `status.md` con marcador `STATUS:` validado por gate | `src/core/gate.py` |
| Observability | trazas JSONL estructuradas (`_telemetry.jsonl`) con coste/turnos/tokens | `src/harness/telemetry.py` |
| Failure attribution | `audit.md` con `failure_type` + `recoverability_lost_at_stage` | `src/core/gate.py`, `agents/reviewer.md` |
| Verification protocol | Deterministic Check Registry (`DC*`) en spec, ejecutado por el reviewer | `src/core/gate.py` |
| Permission boundary | HITL (aprobación humana) + gates por modo | `src/mission/hitl.py` |
| Intervention logger | `write_intervention` clasifica cada decisión HITL | `src/harness/telemetry.py`, `src/mission/hitl.py` |

### Deterministic check registry (corazón de H3)
- **Del paper:** convertir el "approved" subjetivo en evidencia, mapeando requisitos a checks ejecutables.
- **En HERO:** el `specifier` declara un `## Deterministic Check Registry` con checks `DC*` ligados a requisitos (`requirement:`, `type:`, `expected:`); el `reviewer` reporta `checks_executed / failed_checks / not_run_checks` en `audit.md`. Validado por el gate (`src/core/gate.py`).

### Verification report estructurado
- **Del paper:** informe de verificación con atribución de fallo.
- **En HERO:** `audit.md` incluye secciones obligatorias `### Evidence Anchoring` (claims soportados vs `unsupported_claims`), `### Gradient Findings` (gradientes textuales), `### Evaluation Hacking Check`, y `failure_type` taxonomizado — todas validadas por gate.

### Trazas e intervention logger
- **Del paper:** observabilidad como trazas estructuradas y registro clasificado de intervenciones humanas.
- **En HERO:** `src/harness/telemetry.py` escribe `_telemetry.jsonl` (`write_phase_event`, `write_intervention`, `estimate_cost_usd`); el refiner (`src/harness/refiner.py`) consume esas trazas para detectar fallos recurrentes.

### Extensiones propias sobre el framework del paper
- **Jerarquía mission > task > burst:** `src/mission/burst_runner.py` (el paper no cubre bursts).
- **Routing de modelo por fase:** `src/core/model_policy.py` (CHEAP/DEFAULT/DEEP).
- **HITL como fast-path a REIMPLEMENT:** `src/mission/hitl.py`.

## 4. No adoptado (y por qué)

- **Entropy auditor dedicado:** no hay un pase específico que audite residuos, *dependency churn* o tests debilitados sobre el diff. Parte de su intención se cubre vía `Evidence Anchoring` y `Evaluation Hacking Check`, pero no como componente independiente.
- **Episode package como deliverable formal:** la información existe distribuida (telemetría + fase `report`), pero no se empaqueta como "episode package" unitario tal y como lo define el paper.
