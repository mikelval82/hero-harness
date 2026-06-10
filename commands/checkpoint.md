Sesion de verificacion activa de comprension. Los checkpoints no son decorativos — son el mecanismo para decidir si avanzar o consolidar.

Documento o tema a verificar: $ARGUMENTS

## Proceso

### 1. Localizar o generar preguntas

Lee el documento indicado por el usuario.

- Si el documento tiene una seccion de checkpoints, preguntas de verificacion o similar, usa esas preguntas.
- Si no tiene preguntas integradas, genera 4-6 preguntas reflexivas basadas en los conceptos clave del documento. Las preguntas deben requerir razonamiento, no memorizacion.

### 2. Sesion socratica — una pregunta a la vez

Presenta cada pregunta al usuario y espera su respuesta. Para cada respuesta:

**Si es correcta y demuestra comprension profunda:**
- Confirma brevemente y pasa a la siguiente.

**Si es parcialmente correcta:**
- Senala que parte es correcta y cual necesita refinamiento.
- Haz una pregunta de seguimiento que guie hacia la comprension completa.
- No avances hasta que quede resuelto.

**Si es incorrecta o superficial:**
- No des la respuesta directamente.
- Reformula la pregunta con una analogia o un escenario concreto que ilumine el concepto.

### 3. Preguntas emergentes

Ademas de las preguntas del documento, genera 1-2 preguntas adicionales basadas en:
- Conexiones con otros temas del proyecto
- Escenarios practicos que apliquen los conceptos
- Trade-offs que el usuario deberia poder razonar

### 4. Veredicto

Al terminar todas las preguntas, emite un veredicto:

- **Comprension solida** — puede avanzar con confianza
- **Comprension parcial** — recomienda re-leer secciones especificas, indicando cuales
- **Necesita consolidacion** — recomienda ejercicios practicos o revision

### 5. Siguiente paso

Segun el veredicto, sugiere:
- Avanzar al siguiente tema (si solida)
- Re-leer secciones especificas y volver a `/checkpoint` (si parcial)
- Practica antes de continuar (si consolidar)
