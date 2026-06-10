Auditoria de contexto de la conversacion actual. Evalua la trayectoria, relevancia y limpieza del contexto acumulado.

Foco opcional: $ARGUMENTS

## Proceso

### 1. Trayectoria

Resume en 3-5 lineas que ha pasado en esta conversacion:
- Objetivo inicial del usuario
- Desviaciones o cambios de direccion
- Estado actual (donde estamos ahora)

### 2. Contexto acumulado

Evalua que informacion relevante se ha acumulado:
- Decisiones tomadas que siguen vigentes
- Descubrimientos del codebase que importan
- Compromisos o acuerdos con el usuario

### 3. Ruido

Identifica contexto que ya no es relevante:
- Exploraciones fallidas o descartadas
- Hipotesis refutadas
- Informacion que fue util en un momento pero ya no aplica

### 4. Recomendacion

Sugiere una de:
- **Continuar** — el contexto esta limpio y enfocado
- **Comprimir** — hay ruido pero el hilo sigue siendo productivo, sugiere que aspectos ignorar
- **Reiniciar** — demasiado ruido acumulado, recomienda nueva conversacion con brief de 3 lineas

### 5. Snapshot (opcional)

Si el usuario lo pide, genera un resumen comprimido del estado actual que
pueda pegar al inicio de una nueva conversacion para retomar contexto.
