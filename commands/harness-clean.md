Limpia el workspace efimero activo del harness engineering.

El workspace activo es `$CLAUDE_HARNESS`. En ejecucion normal apunta a
`$HOME/.harness/<project>/<branch-safe>/`; no debe apuntar al proyecto target.

$ARGUMENTS

## Proceso

1. Verifica que `$CLAUDE_HARNESS` esta definido y que existe:
   - Si existe, lista su contenido para mostrar al usuario que se va a eliminar.
   - Si no existe, informa que el workspace ya esta limpio.
   - Si no esta definido, informa que no hay workspace activo.

2. Si existe, ejecuta:
   ```bash
   rm -rf $CLAUDE_HARNESS/
   ```

3. Confirma la limpieza al usuario.
