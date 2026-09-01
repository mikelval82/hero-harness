# L3 — Skill library gobernada

La biblioteca registra skills versionadas con manifest de permisos, receipts y
fecha. Solo se recuperan entradas no revocadas y completas. El contenido
recuperado se marca como dato no confiable: no puede convertirse en instrucciones
de sistema ni ampliar la autoridad runtime por aparecer en el índice.

La promoción se representa como una propuesta con identidad estable y requiere
aprobación humana; la API de esta entrega siempre devuelve `apply=false`. Los
tests sandbox y la revocación son requisitos previos a una promoción persistente.
