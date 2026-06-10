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

## 3. Qué adoptamos en HERO y cómo está implementado

La idea central de Agent Hospital —agentes que mejoran sin fine-tuning vía **memoria externa**, con la separación *case base* (éxitos) / *experience base* (fallos)— está implementada en HERO como memoria persistente cross-misión bajo `~/.harness-memory/{project_key}/`.

### Mission case base (casos de éxito)
- **Del paper:** persistir trazas de tareas resueltas y recuperarlas por similitud al afrontar una tarea nueva.
- **En HERO:** `src/harness/case_base.py` guarda cada misión `APPROVED` como caso en `mission-cases.jsonl` (`save_approved_mission_case`, `build_mission_case`) y recupera los más parecidos al brief actual con `retrieve_cases` (similitud léxica tipo TF-IDF, no embeddings). Los casos se inyectan en las fases como `retrieved-cases.md`.

### Experience base (modos de fallo recurrentes)
- **Del paper:** abstraer reglas a partir de los fallos para no repetirlos.
- **En HERO:** dos mecanismos complementarios. (1) `src/harness/project_memory.py` mantiene `PROJECT_MEMORY.md` con una sección **Recurring Failure Modes** que se inyecta en cada fase (`project-memory.md`). (2) El **refiner post-misión** (`src/harness/refiner.py`) extrae firmas de fallo recurrentes (`failure_type@stage`, recurrencia ≥ 2) desde `_telemetry.jsonl` y los `audit.md`, y propone reglas/endurecimientos **sin aplicarlos**.

### Retrieval al inicio de tarea
- **Del paper:** recuperar conocimiento relevante antes de actuar.
- **En HERO:** el `researcher`, `specifier` y `reviewer` reciben `retrieved-cases.md`, `retrieved-skills.md` y `project-memory.md` como artefactos de entrada (composición declarativa en `PHASE_REGISTRY`, `src/core/context.py`; staging en `src/harness/`).

### LLM frozen + memoria externa
- **Del paper:** el modelo no se reentrena; toda la mejora vive en la memoria.
- **En HERO:** los modelos son frozen (routing por fase en `src/core/model_policy.py`) y la mejora se acumula exclusivamente en la memoria persistente y la skill library (`src/harness/skill_library.py`, skills marcadas `status: verified`).

## 4. No adoptado (y por qué)

- **Simulacrum / entorno sintético:** HERO trabaja sobre el entorno real (filesystem, git, tests). Generar tareas de código etiquetadas es barato (commits reales), así que no hay simulacrum.
- **Scaling laws sobre decenas de miles de ejemplos:** fuera de presupuesto; requeriría infraestructura para correr el agente sobre ~50k tareas.
- **Generación de datos sintéticos por "departamento":** sin equivalente útil en un harness de código.
- **Validación de regla en caso held-out estricta:** la case base solo persiste misiones `APPROVED` y las skills se marcan `verified`, pero no hay un protocolo formal de validación de cada regla en un caso futuro similar (baja densidad de tareas similares).
