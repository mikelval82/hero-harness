Meta-skill para crear nuevos slash commands. Te guia en el diseno y escritura de un command bien estructurado.

Idea para el nuevo skill: $ARGUMENTS

## Proceso

### 1. Definir el proposito

Responde estas preguntas (explora el codebase si ayuda):
- Que problema resuelve este skill?
- Cuando lo invocaria un usuario?
- Que inputs necesita ($ARGUMENTS)?
- Que outputs produce?

### 2. Clasificar

Determina el tipo de skill:
- **Autonomo**: se ejecuta sin subagentes (como `/grill`, `/diagnose`)
- **Orquestador**: lanza subagentes via el patron leader (como `/brainstorm`, `/implement-task`)
- **Modo**: cambia el comportamiento de la sesion (como `/caveman`)

### 3. Estructurar

Genera el archivo `.md` del command con esta estructura:

```markdown
[Descripcion de una linea del proposito]

[Input del usuario]: $ARGUMENTS

## [Secciones del proceso]

### Paso 1 — [nombre]
[instrucciones claras]

### Paso 2 — [nombre]
[instrucciones claras]

## Reglas
[restricciones y comportamiento]
```

### 4. Ubicar

- Si el skill es de uso personal (transversal a proyectos): `~/.claude/commands/[nombre].md`
- Si el skill es especifico de un proyecto: `.claude/commands/[nombre].md`

### 5. Probar

Sugiere un escenario de prueba para validar que el skill funciona correctamente.

## Principios de buen diseno

- **Pequeno**: un skill = un proposito. Si necesitas dos, crea dos.
- **Componible**: el output de un skill puede ser input de otro.
- **Autonomo**: el skill incluye toda la informacion que necesita, sin dependencias implicitas.
- **Adaptable**: usa $ARGUMENTS para flexibilidad, no hardcodees valores.
