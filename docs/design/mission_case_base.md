# Mission case base persistente

**Checkpoint:** tarea 15

La case base guarda misiones aprobadas como casos concretos y recuperables por similitud. A diferencia de `project-memory.md`, que contiene reglas y notas duraderas, la case base conserva trazas episodicas: "esta mision concreta se resolvio asi".

## Ubicacion

```text
$HOME/.harness-memory/<project-key>/cases.jsonl
```

Durante `setup_harness(...)`, el runner crea tambien:

```text
$CLAUDE_HARNESS/retrieved-cases.md
$CLAUDE_HARNESS/_project_cases_path
```

`retrieved-cases.md` contiene los casos aprobados mas similares a la tarea actual y se inyecta como `MISSION_CASES` en las fases agenticas.

## Esquema minimo

Cada linea de `cases.jsonl` es un JSON:

```json
{
  "case_id": "uuid estable",
  "created_at": "2026-05-28T12:00:00",
  "project": "repo",
  "project_dir": "C:/path/repo",
  "task": "peticion original",
  "branch": "feature/x",
  "mode": "full",
  "outcome": "APPROVED",
  "task_summary": "Total: ...",
  "brief_summary": "...",
  "spec_summary": "...",
  "plan_summary": "...",
  "decisions_summary": "...",
  "files_changed": ["src/example.py"],
  "audit_verdict": "APPROVED",
  "audit_summary": "...",
  "report_summary": "...",
  "validation_summary": "pytest ... -> PASS",
  "telemetry": {"total_tokens": 1234},
  "lessons": ["decision/risk/failure/constraint reusable"],
  "retrieval_text": "texto compacto para similitud"
}
```

## Politica de guardado

Se guarda un caso solo si:

- La mision no esta bloqueada.
- `tasks.json` existe y todas las tareas estan `completed`.
- Si existe `audit.md`, el veredicto es `APPROVED`.

No se guardan misiones fallidas, parciales o bloqueadas.

## Recuperacion simple

El MVP usa similitud lexical barata:

1. Tokeniza la tarea actual.
2. Tokeniza `retrieval_text`, task, brief/spec/plan summaries y lessons de cada caso.
3. Calcula overlap normalizado.
4. Escribe top-k en `retrieved-cases.md`.

Esto no es una vector DB ni BM25 completo; es suficiente para demostrar recuperacion simple y medible antes de invertir en retrieval mas pesado.

## Uso por agentes

Los casos recuperados son ejemplos concretos, no autoridad. Un agente puede reutilizar patrones de archivos, checks o decisiones solo si el codebase actual confirma que siguen aplicando.
