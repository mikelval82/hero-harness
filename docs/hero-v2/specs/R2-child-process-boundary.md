# R2 — Límite de procesos hijos y credenciales

## Objetivo

Una herramienta invocada por un proveedor no debe volver a entregar su texto a
un intérprete de shell ni recibir las credenciales con las que HERO conversa con
proveedores, Telegram o el plano de control.

## Contrato v2

`Bash` acepta solo una lista de comandos permitidos. La política analiza el
texto una vez y entrega al executor pipelines de `argv`; cada proceso externo se
lanza con `shell=False`. El runtime implementa `|`, `&&` y `||` propagando
stdout, exit code y directorio actual sin pedirle esa semántica a un shell.
Redirecciones, `;`, trabajos en segundo plano, sustituciones, heredocs y rutas
de ejecutable explícitas se rechazan antes de ejecutar nada.

El entorno hijo se construye de nuevo a partir del entorno del runtime y elimina
como mínimo `ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY`, `TELEGRAM_TOKEN`,
`TELEGRAM_CHAT_ID` y `CLAUDE_HARNESS`; también elimina nombres que contengan
marcadores de secreto, token, API key, password, credential o worker. La
filtración es compartida por Bash y la validación.

Review no recibe Bash. Recibe `RunValidation(check_id="target_validation")`,
que selecciona uno de los nombres fijos `mission-validate.*` y ejecuta el argv
correspondiente, sin aceptar un comando del proveedor ni leerlo de `spec.md`.

## Criterios de aceptación

- Un proceso externo de Bash recibe lista argv y `shell=False`.
- Pipes y los operadores `&&`/`||` se ejecutan en el runtime; redirecciones y
  separadores de shell se rechazan.
- Los secretos y variables de control de HERO no llegan a Bash ni a
  RunValidation.
- Solo Review anuncia RunValidation; las demás fases son rechazadas por el
  registry antes de ejecutar la herramienta.
- Las pruebas cubren escape de rutas, ejecución de binario explícito,
  redirección, entorno hijo, pipes y la selección fija de validación.

## Límites deliberados

Esto no es un sandbox de sistema operativo. Los procesos permitidos continúan
ejecutándose con los permisos del usuario y un `mission-validate.*` modificado
en el proyecto sigue siendo código del proyecto: R2 controla la selección del
comando y elimina entrada arbitraria del proveedor, pero no certifica el
contenido de la validación. R3/R5 deberán aportar preflight, CI y evidencia de
validación independiente.
