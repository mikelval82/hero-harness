# Paper 02 — Agent Hospital: A Simulacrum of Hospital with Evolvable Medical Agents

**Autores:** Junkai Li et al. (Tsinghua AIR)
**arXiv:** 2405.02957v3, enero 2025
**Tipo:** Paper aplicado / sistema (sí tiene experimentos)
**Fichero:** `papers/AGENT HOSPITAL - a simulacrum of hospital with evolvable medical agents.pdf`

---

## 1. Tesis del paper en una frase

Construir un **simulacrum** del entorno operativo (hospital virtual con 32 departamentos y 339 enfermedades) para que agentes con LLM **congelado** evolucionen sin datos etiquetados manualmente, mediante dos memorias persistentes: una **case base** (casos exitosos) y una **experience base** (reglas extraídas de fallos). Transfieren competencia del mundo virtual al real (MedQA benchmark).

Es un paper de **dominio médico**, pero las primitivas son generales.

---

## 2. Las dos piezas: SEAL y MedAgent-Zero

### SEAL = Simulacrum-based Evolutionary Agent Learning

1. **Simulacrum construction:** entorno simulado con eventos (Disease Onset → Triage → Registration → Consultation → Examination → Diagnosis → Dispensary → Convalescence → Follow-up). Datos sintéticos generados acoplando LLM con base de conocimiento de dominio.
2. **Agent evolution:** los agentes aprenden actuando en el simulacrum sin retraining del LLM.

### MedAgent-Zero — el mecanismo de evolución (LO RELEVANTE)

LLM **frozen**. Dos memorias persistentes que crecen con la práctica:

| Memoria | Tipo cognitivo | Contenido | Cuándo se actualiza |
|---------|----------------|-----------|---------------------|
| **Medical case base** | Episódica | Casos completos (síntomas, exámenes, diagnóstico correcto) | Tras tratamiento **exitoso** |
| **Experience base** | Semántica / procedimental | Reglas extraídas de fallos ("pacientes >50 con varicela previa → sospechar Herpes Zoster") | Tras tratamiento **fallido**: reflexión genera regla → se valida en caso similar → si funciona, se persiste; si no, se descarta |

En inferencia, el agente recupera de ambas memorias por similitud y las inyecta en el contexto antes de decidir.

### Resultados empíricos

- Diagnóstico cardiología (rheumatic heart disease): **9% → 82%** tras evolución.
- Respiratorio: 66% → ~92% tras 10.000 pacientes; mejora asintótica hasta 50.000.
- En MedQA real (USMLE), supera a MedAgents, CoT, Medprompt con GPT-4o **sin usar el training set del benchmark**.
- Curva de scaling: aprendizaje rápido los primeros 10k pacientes, retornos decrecientes después.

---

## 3. Mapeo a nuestro harness

| Pieza Agent Hospital | Análogo en nuestro harness | Estado |
|----------------------|----------------------------|--------|
| Simulacrum del entorno | — | ❌ No tenemos. Trabajamos sobre el entorno real (filesystem, git, tests). |
| Case base (éxitos) | — | ❌ `context-cold.md` es **per-mission**, no cross-mission. Cuando termina una misión, no se persiste nada que sirva para la siguiente. |
| Experience base (reglas de fallos) | — | ❌ Mismo problema. El `audit.md` y los REIMPLEMENT loops se pierden al cerrar workspace. |
| Reflexión sobre fallo → regla | Reviewer produce `audit.md`, reimplement aplica fixes | ⚠️ Parcial e in-task. No hay extracción de regla generalizable. |
| Retrieval por similitud al inicio de tarea | — | ❌ El researcher/specifier construyen contexto desde cero cada misión. No hay "tareas parecidas que hiciste antes". |
| Validación de regla en caso held-out | — | ❌ |
| LLM frozen + memoria externa | ✅ usamos LLM frozen (Sonnet) + workspace efímero | OK la parte de frozen; la memoria externa persistente no existe. |

**Gap dominante:** todo el aprendizaje ocurre **dentro** de una misión y se descarta al final. No hay memoria que evolucione con el uso del harness.

---

## 4. Aplicabilidad real al harness

### 4.1 Lo que NO se traduce

- **El simulacrum como tal.** No tiene sentido simular código sintético: SWE-bench, instancias reales de GitHub, etc. ya proporcionan distribución real. El simulacrum de Agent Hospital existe porque generar pacientes etiquetados es caro; generar tareas de coding etiquetadas no lo es (son commits reales).
- **Scaling laws de 50.000 ejemplos.** Implícitamente requiere infraestructura para correr el agente sobre decenas de miles de tareas. Fuera de presupuesto.
- **Generación de datos sintéticos por departamento.** No tiene equivalente útil.

### 4.2 Lo que SÍ se traduce — case base + experience base cross-mission

Esta es la idea importante. Adaptación al harness:

| Pieza original | Adaptación a harness de código |
|----------------|-------------------------------|
| Case base de pacientes diagnosticados | **Mission case base**: por cada misión APPROVED, persistir `{brief, spec, plan, diff_resumen, lecciones}` |
| Experience base de reglas | **Engineering rules base**: tras cada REIMPLEMENT (audit fallido), extraer "el reviewer rechazó X porque Y → regla: cuando hagas tareas tipo X, comprueba Y antes" |
| Retrieval al diagnosticar | Inyectar en `researcher` / `specifier` los N casos más similares al brief actual |
| Validación de regla en caso similar | Marcar una regla como "verificada" cuando una misión posterior con tarea similar la siguió y pasó |
| Distinción case/experience | Misma distinción: casos = trazas concretas; reglas = patrones abstraídos |

### 4.3 Diferencias estructurales importantes

- Agent Hospital tiene **ground truth** automático (la enfermedad correcta es conocida por el simulacrum, oculta al doctor). En nuestro harness el "ground truth" es el reviewer (APPROVED) y los tests. Igualmente verificable.
- La política de validación de reglas (probar en 1 caso similar; si no funciona, descartar) es **agresivamente simple** y depende de tener muchos casos similares. En misiones de código la cola de tareas es más diversa → validación más difícil.

---

## 5. Análisis Riesgo · Beneficio · Impacto · Novedad

### Como aporte al **harness**

| Mejora propuesta | Coste (Riesgo) | Beneficio | Impacto | Novedad |
|------------------|----------------|-----------|---------|---------|
| **Mission case base persistente cross-misión** (retrieval por similitud sobre brief/spec) | Medio. Requiere storage persistente fuera de `$CLAUDE_HARNESS`, indexación (embedding o BM25), política de qué guardar | Alto si el usuario lanza misiones repetitivas; bajo si cada misión es totalmente nueva | Medio-Alto en uso continuado | Media (RAG de tareas previas es común; lo nuevo es **integrarlo en un harness multi-fase**) |
| **Experience base: extracción de reglas tras audit fallido** | Alto. Necesita un agente nuevo "rule-extractor", política de validación, garbage collection de reglas mal calibradas | Medio. Útil si los fallos son recurrentes ("siempre se me olvida actualizar el changelog") | Medio | Alta — pocos harnesses tienen esto formalizado con validación |
| **Validación de regla en caso held-out** | Alto. Requiere capacidad de identificar "caso similar futuro" y atribuir éxito/fallo a la regla concreta | Bajo a corto plazo (poca densidad de tareas similares); alto a muy largo plazo | Bajo en el horizonte realista | Alta como contribución de research |
| **Curvas de scaling de mejora con N tareas** | Alto. Implica correr el harness sobre cientos/miles de tareas reales | Bajo para mejora del harness; alto para el paper como evidencia | Alto para el paper, bajo para la herramienta | Media |

### Como aporte al **paper / benchmark**

| Dimensión | Valoración |
|-----------|------------|
| **Validez de la analogía** | Media. SEAL es un patrón concreto de su dominio. Trasplantarlo entero al benchmark de code-gen es forzado. |
| **Inspiración para hipótesis** | Alta. Hipótesis derivable: "Un harness con case base persistente alcanza más rápido APPROVED en misiones similares posteriores que un harness sin ella" — esto es **ablativo, medible, defendible**. |
| **Inspiración para diseño del benchmark** | Media-Alta. Sugiere medir **transferencia entre tareas relacionadas**, no sólo accuracy puntual. Eje nuevo: "¿el harness mejora con la experiencia, o cada misión es un partido nuevo?" |
| **Como SOTA contra el que competir** | No aplica. Dominio distinto. |
| **Como cita en related work** | Alta. Ejemplo concreto de evolución sin retraining, con resultados publicados en venue serio (Tsinghua AIR). |

---

## 6. Decisiones recomendadas

### Para el **harness**

1. **No** construir un simulacrum de código. SWE-bench y commits reales sirven mejor.
2. **Sí** explorar una **mission case base persistente** como skill independiente (no como cambio core del runner). Ubicación: fuera de `$CLAUDE_HARNESS`, p.ej. `$HOME/.harness-memory/` con esquema `{project, brief_hash, brief, spec, plan, audit_summary, outcome}`. Retrieval simple (BM25 sobre brief+spec) inyectado por el `researcher`.
3. **No** invertir en experience base (extracción de reglas) hasta tener la case base funcionando y datos suficientes para evaluar si las reglas transfieren. Riesgo alto de generar "reglas zombi" no calibradas.
4. **Sí** medir la curva de mejora cross-mission si llegamos a tener ≥30 misiones reales del mismo proyecto. Es el experimento natural a publicar si la case base funciona.

### Para el **paper / benchmark**

- **Citar** Agent Hospital como ejemplo precedente de "agentes que mejoran sin fine-tuning vía memoria externa, con scaling laws empíricas".
- **Considerar** añadir al benchmark un **eje de transferencia**: ejecutar el harness sobre dos tareas relacionadas en secuencia y medir si la segunda se resuelve más rápido / mejor con case base activada vs desactivada. Es un experimento ablativo limpio, barato y novedoso.
- **No tratar** SEAL como SOTA competidor — está en otro dominio.

---

## 7. Veredicto franco

- **Como sistema de medicina:** impresionante en alcance, números bonitos (9%→82% es titular), pero el resultado en MedQA hay que tomarlo con pinzas — el "no usamos el training set" es estrictamente cierto pero la base de conocimiento médica que alimenta el simulacrum cubre el mismo material que MedQA examina; el paper minimiza este solapamiento.
- **Como arquitectura general:** la dupla **case base + experience base** es una de las pocas formas concretas y verificables de "agentes que mejoran con el uso". Es lo mejor del paper.
- **Como inspiración para nosotros:** una idea concreta vale la pena (mission case base cross-misión); el resto (simulacrum, generación sintética) no aplica.
- **Riesgo de copia ingenua:** alto si trasplantamos SEAL entero. Bajo si extraemos sólo la persistencia de casos como skill opcional.
- **Honestamente:** el paper es 70% medicina y 30% arquitectura de agentes. Para nuestros fines, el 30% es lo que importa, y lo que importa coincide bastante con ideas que ya están en Voyager (skill library) y Reflexion (verbal reinforcement). El valor diferencial es la **separación explícita** case (éxito) vs experience (fallo) con validación.

**Acción concreta sugerida:** anotar **mission case base persistente cross-misión** como candidato a explorar **después** de las mejoras de paper 01 (diagnosis gate, spec re-injection). Tratar como skill opcional, no como cambio del runner.
