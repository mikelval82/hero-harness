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

## 3. Mapeo a nuestro harness (1-a-1)

| 11 componentes del paper | Nuestro harness | Estado |
|--------------------------|-----------------|--------|
| Task interface | `brief.md` (griller) + `spec.md` (specifier) | ✅ Sólido |
| Context manager | `build_code_graph`, `context-hot.md`, `context-cold.md` | ✅ Sólido |
| Tool registry | tools por fase en `PHASE_REGISTRY` (DEFAULT/IMPL/REVIEW) | ✅ |
| Project memory | `~/.claude/AGENTS.md`, `CONTEXT.md`, `CHECKPOINTS.md`, `commands/` | ⚠️ Existe pero **per-installation**, no per-proyecto. No tenemos AGENT_GUIDE / ARCHITECTURE / KNOWN_FAILURES por proyecto target. |
| Task state | `status.md` | ✅ |
| Observability | logs en `$CLAUDE_HARNESS` | ⚠️ Existen, pero **no estructurados como traces JSONL**. |
| Failure attribution | `audit.md` del reviewer | ⚠️ Es NL, no clasificado por taxonomía de 8 tipos. |
| Verification protocol | reviewer + reimplement loop | ⚠️ Sin **deterministic check registry** explícito. No mapeamos requisitos del spec a checks individuales. |
| Permission boundary | HITL (Telegram/stdin), gates por modo | ✅ |
| Entropy auditor | — | ❌ No existe. Nadie audita residuos, dependency churn, tests debilitados. |
| Intervention logger | HITL deja rastro pero no clasificado | ❌ No marcamos "avoidable / not-avoidable" ni mapeamos a componente faltante. |

**Posición en la escalera H0–H3:** somos aproximadamente **H2.7**. Tenemos casi todo H2 + reviewer (que es H3 parcial) pero falta el corazón de H3: deterministic checks ligados a requisitos, bug-reproduction protocol explícito, structured verification report, entropy audit, intervention classification.

---

## 4. Aplicabilidad — desglose por bloques

### 4.1 Para el **harness** (implementación)

| Mejora derivada del paper | Coste | Beneficio | Impacto | Novedad |
|---------------------------|-------|-----------|---------|---------|
| **Trazas JSONL estructuradas** (8 tipos) en lugar de logs sueltos | Medio | Alto. Habilita métricas reproducibles, debug, paper | Alto | Baja (es ingeniería) |
| **Deterministic check registry** que mapea requisitos del `spec.md` a checks ejecutables, leído por reviewer | Medio-Alto | Muy alto. Convierte "approved" subjetivo en evidencial | Muy alto | Media |
| **Project memory por target-project** (AGENT_GUIDE, ARCHITECTURE, KNOWN_FAILURES) dentro del repo target, no en `~/.claude/` | Bajo | Alto si el usuario lo mantiene; el harness puede ayudar a generarlo en la primera misión | Alto a largo plazo | Baja (es práctica de la industria) |
| **Intervention logger clasificado** (mapea cada HITL a "qué componente del harness habría evitado esto") | Bajo | Alto. Convierte HITL en señal diagnóstica para mejorar el propio harness | Alto | Alta |
| **Entropy auditor** (post-pass sobre el diff: docs obsoletas, residuos, tests debilitados, dependency churn) | Medio | Medio. Importante en proyectos serios | Medio | Media |
| **Bug-reproduction protocol explícito** antes de editar en tareas de bug-fix | Bajo | Alto en bug-fix; combate "patching aleatorio". Es exactamente el `R-CG1 diagnosis gate` de paper 01 reformulado | Alto | Baja |
| **Failure attribution clasificado** (`audit.md` con campo `failure_type ∈ {Fcontext, Ftool, ...}`) | Bajo | Alto. Convierte audit NL en dato estructurado | Alto | Media |
| **Episode package** como deliverable final por misión | Medio | Alto para el paper (es la unidad de evaluación) | Alto para el paper, medio para la herramienta | Baja |

### 4.2 Para el **paper / benchmark** (esto es lo importante)

Este paper nos da **toda la infraestructura conceptual** del benchmark prácticamente gratis.

| Pieza del paper | Cómo la usamos en nuestro benchmark |
|-----------------|--------------------------------------|
| Ecuación $C_{sys}=F(C_{model}, C_{harness}, C_{env}, T)$ | Justifica formalmente nuestra tesis: **mismo modelo, distinto harness, distinto outcome**. |
| Escalera H0–H3 | **C1 Raw ≈ H0, C2 Loop tonto ≈ H1, C3 Harness ≈ H2/H3**. Nuestro benchmark se convierte en una validación empírica poblacional de la escalera del paper (que ellos sólo ilustran con 1 tarea). |
| 5 outcomes | Reemplaza el binario pass/fail en H1 "correctness" del research_plan. |
| 8 trazas + episode package | Es exactamente la unidad de análisis que necesitamos. |
| M-HIR | Métrica de calidad del harness perfecta para nuestra hipótesis H2 (calidad estructural). |
| Taxonomía de 8 fallos | Permite **análisis por causa** en lugar de sólo "C1 falla más" — narrativa mucho más fuerte. |
| 11 componentes + 5 principios | Vocabulario que estructura la sección de related work y la descripción del C3. |

### 4.3 Riesgo de derivar demasiado

- Si abrazamos su framework entero, nuestro paper se lee como "validación empírica de Zhong & Zhu 2026". Eso puede ser **bueno** (cuento limpio, contribución clara) o **malo** (parece derivativo).
- **Mitigación:** posicionarnos como complementarios. Ellos: framework + 1 tarea ilustrativa, sin estudio poblacional. Nosotros: estudio poblacional sobre N tareas reales con 3 contenders, midiendo justo lo que su framework predice. **"Their framework, our evidence."**
- También podemos **extender** el framework: ellos no cubren `mission > task > burst` (jerarquía), ni HITL como fast-path REIMPLEMENT, ni hot/cold context. Esas son contribuciones diferenciadas nuestras.

---

## 5. Análisis Riesgo · Beneficio · Impacto · Novedad — resumen

### Como aporte al **harness**

1. **Trazas JSONL + deterministic check registry + entropy auditor** — paquete coherente, coste medio, beneficio alto, defendible empíricamente.
2. **Intervention logger clasificado + failure attribution clasificada** — coste bajo, beneficio alto. Casi gratis y abre puerta a métricas serias.
3. **Project memory por target-project** — coste bajo, valor alto.

### Como aporte al **paper**

**Crítico.** Es la cita más importante de toda la colección. Da:
- vocabulario,
- formalización,
- protocol de evaluación,
- métrica diferenciadora (M-HIR),
- una escalera natural para mapear nuestros 3 contenders.

---

## 6. Decisiones recomendadas

### Para el **harness** (orden de implementación)

1. **Failure attribution clasificada** en el reviewer (`audit.md` con campo `failure_type`) — coste mínimo, beneficio inmediato.
2. **Intervention logger** con clasificación `{avoidable_by_harness: yes/no, missing_component: <which>}` — coste bajo, datos directos para mejorar.
3. **Trazas JSONL estructuradas** (action, tool, context, verification, intervention, entropy, outcome). Refactor que vale la pena porque desbloquea todo lo demás.
4. **Deterministic check registry** ligado al `spec.md` — el `specifier` produce una lista de checks ejecutables; el `reviewer` los ejecuta. Es la versión madura del "verification gate".
5. **Entropy auditor** como fase opcional post-IMPLEMENT — diff diff, busca residuos, docs obsoletas, tests debilitados.
6. **Project memory por target-project** — más cultural que técnico; documentar la práctica.

### Para el **paper**

- **Adoptar explícitamente** el framework H0–H3 como eje del experimento principal. Reescribir las hipótesis H1–H5 del `research_plan` en su vocabulario.
- **Adoptar** los 5 outcomes y la taxonomía de 8 fallos como dimensiones de análisis.
- **Citar a Zhong & Zhu 2026** como base teórica y posicionarnos como "primer estudio poblacional bajo este framework".
- **Diferenciarnos** explícitamente: ellos ilustran con 1 tarea controlada; nosotros aportamos evidencia poblacional + extensión del framework con jerarquía mission/task/burst + HITL fast-path.

---

## 7. Veredicto franco

- **Calidad del paper:** sólida. Está bien escrito, define cosas con precisión, distingue su propuesta de prompts, agent frameworks, ACIs y agent OSes. La debilidad obvia: una sola tarea de ilustración. Los propios autores lo reconocen explícitamente — no pretende ser estudio empírico.
- **Nivel de novedad real:** medio-alto. La industria (OpenAI Codex, Microsoft) ya converge informalmente en estas ideas; el aporte de Zhong & Zhu es **nombrarlas y darles estructura empírica ablativa**. Eso es lo que precisamente faltaba.
- **Para nosotros:** este paper transforma el problema. En lugar de "diseñar un benchmark desde cero", ahora tenemos un framework establecido que **podemos llenar con datos**. La pregunta de research del paper propio se vuelve más nítida: *"¿Hasta qué punto el efecto harness predicho por H0→H3 se confirma empíricamente sobre N tareas reales con un solo modelo?"*
- **Riesgo principal:** parecer derivativos. Mitigación: enmarcar como validación + extensión, no como propuesta de framework competidor.

**Acción concreta sugerida:**
1. Re-escribir el `research_plan/research_plan.md` integrando la escalera H0–H3 como eje principal.
2. Implementar primero **failure attribution clasificada** e **intervention logger** porque son baratos y necesarios para el benchmark.
3. Citar Zhong & Zhu 2026 en la sección de fundamentos del paper y posicionarnos como complemento empírico, no como competencia.
