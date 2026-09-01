# O2 — Obligaciones deterministas de validación

Cada contrato inmutable de tarea materializa una `ValidationObligation` por
criterio de aceptación. Su identificador de criterio (`ACC:<node>:<ordinal>`)
preserva el vínculo aunque el criterio no tuviese previamente un ID de requisito.
Las obligaciones actuales son `trusted_command` y apuntan solamente a
`target_validation`.

`RunValidation` resuelve ese identificador en una allowlist propiedad del
runtime; no recibe un comando ni ejecuta texto que haya escrito el proveedor.
La ejecución deja un receipt atómico en
`validation-evidence/target_validation.json`: estado, instante, script,
exit code y huella/longitud de salida. La salida completa no se persiste como
evidencia para no convertir el receipt en un canal de secretos.

Al cerrar Review, el gate conserva las comprobaciones Markdown y además lee el
contrato y sus receipts. `pass` permite continuar; `fail` bloquea; una ausencia
de receipt o `not_run` bloquea explícitamente. Las futuras obligaciones
`static`, `browser` y `manual` deberán aportar evidencia alternativa tipada
antes de poder permitir un `not_run`; no pueden degradar este comando confiable.
