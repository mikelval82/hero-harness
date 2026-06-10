Sesion de alineacion para una mision autonoma. Tu objetivo es alcanzar un entendimiento compartido completo con el usuario sobre la tarea, y luego guardar el resultado en disco.

Tarea a alinear: $ARGUMENTS

## Proceso

### 1. Interrogar — una pregunta a la vez

Haz las preguntas **de una en una**, esperando feedback antes de continuar.

- Si una pregunta puede responderse explorando el codebase, **explora tu mismo**.
- **Desafia** asunciones cuando detectes inconsistencias o riesgos.
- Inventa **escenarios concretos** para stress-testear las decisiones.
- Cuando una decision se cristalice, resumela en una frase antes de continuar.

### 2. Cristalizar

Cuando todas las ramas esten resueltas, presenta un resumen estructurado y pide confirmacion.

### 3. Guardar y terminar

Tras la confirmacion del usuario, escribe el brief en `$CLAUDE_HARNESS/brief.md` (usa la variable de entorno CLAUDE_HARNESS para la ruta) con este formato:

```markdown
# Mission Brief

**Task:** {descripcion refinada}
**Date:** {timestamp}

## Objective
{Que se quiere lograr, en 2-3 frases}

## Key Decisions
{Lista de decisiones cristalizadas durante la alineacion}

## Scope
- **Incluido:** {que entra}
- **Excluido:** {que no entra}

## Constraints
{Restricciones tecnicas, de tiempo, o de dependencias}
```

Despues de guardar el archivo, confirma al usuario que el brief esta guardado y que la fase autonoma comenzara automaticamente. Termina la sesion.
