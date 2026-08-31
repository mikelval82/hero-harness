# R4 — Telegram seguro por misión

## Contrato v2

Un token de Telegram solo puede tener un listener HERO propietario. El lock es
no bloqueante, multiproceso y se deriva de un SHA-256 no reversible del token;
el token nunca aparece en paths, logs ni artefactos.

El offset es global por token y se escribe atómicamente antes de entregar una
actualización al CommandBus. En cada inicio se descarta el backlog de downtime y
se persiste el siguiente offset. La semántica es at-most-once: ante una caída se
puede perder un comando, pero no repetirlo contra otra misión.

El listener ofrece `stop()`, usa long polling corto y clasifica HTTP 401/403/409
como fatal; errores de red, timeout y otros errores se degradan con backoff
exponencial limitado. Al detenerse libera el lock.

`TELEGRAM_TOKEN` y `TELEGRAM_CHAT_ID` son un par obligatorio. Solo se acepta un
mensaje privado cuyo chat y emisor coincidan con el chat configurado. Las
lecturas pueden omitirse el destino; los comandos que mutan el CommandBus
requieren el target exacto de la misión activa, por ejemplo
`/abort @project:feature-safe`.

## Límite deliberado

At-most-once favorece que un comando no se ejecute por error frente a la entrega
garantizada. La correlación se basa en el `mission_tag` activo y no crea una
sesión criptográfica de usuario; el chat privado configurado sigue siendo la
identidad autorizada. La gestión de secretos del entorno se mantiene fuera del
listener.
