Mapa rapido de orientacion en el codebase. Util cuando estas perdido en el codigo o necesitas entender la estructura antes de hacer cambios.

Foco opcional: $ARGUMENTS

## Proceso

### 1. Vista de pajaro

Genera un mapa de la estructura del proyecto:
- Directorios principales y su proposito
- Archivos clave (entry points, configuracion, tests)
- Dependencias externas relevantes

### 2. Modulos y relaciones

Si se especifica un foco (archivo, funcion, modulo):
- Lista todos los callers (quien llama a este codigo)
- Lista todas las dependencias (que usa este codigo)
- Muestra la cadena de llamadas relevante

Si no se especifica foco:
- Identifica los modulos principales y sus relaciones
- Genera un diagrama Mermaid de alto nivel

### 3. Puntos de entrada

Identifica:
- Entry points de la aplicacion
- Endpoints o interfaces publicas
- Tests existentes y su cobertura

### 4. Presentar

Presenta el mapa de forma concisa. No listes todos los archivos — resalta
la estructura y las relaciones que ayudan a orientarse.
