# Telegram single-mission: contrato de diseño

## Objetivo

Telegram es un canal opcional de notificación y control remoto para una única
misión. Un mismo token de bot no puede controlar dos misiones concurrentes. El
harness puede seguir ejecutando otras misiones, pero estas continuarán sin
Telegram si el token ya está ocupado.

La integración vive dentro del proceso de la misión. No existe resolución de
misiones por tags, registro global de misiones ni comunicación mediante archivos
`_cmd_*`.

## Invariantes

1. Todo comando actúa exclusivamente sobre el `harness`, la cola y el estado de
   la misión que posee el listener.
2. Los comandos mutadores se validan antes de encolarse y nunca se difieren para
   otro estado futuro.
3. Cada espera humana tiene un `interaction_id`; solo la primera respuesta
   válida puede reservarla y el consumidor vuelve a verificar ese identificador.
4. Una notificación de espera solo se marca como enviada cuando Telegram confirma
   todos sus fragmentos.
5. Los updates se procesan como máximo una vez. En cada arranque del listener se
   descarta el backlog previo para impedir que comandos de una misión o periodo de
   inactividad afecten a la misión que comienza.
6. `/ask` solo puede leer el proyecto y el workspace mediante `Read`, `Glob`,
   `Grep` y `CodeGraph`; no dispone de escritura ni Bash.
7. Telegram solo acepta comandos del chat privado configurado.

## Ownership y ciclo de vida

- El owner se protege mediante un lock de sistema operativo por hash del token en
  `~/.harness/`. El descriptor se mantiene abierto hasta el cleanup y el archivo
  estable no se elimina.
- Si el lock ya está ocupado, la misión continúa sin listener ni notificaciones
  Telegram y lo informa claramente por consola y log.
- Si solo está configurada una de `TELEGRAM_TOKEN` o `TELEGRAM_CHAT_ID`, el
  arranque falla por configuración incoherente.
- El listener tiene un `stop()` idempotente. Errores permanentes de autenticación
  o conflicto se hacen visibles; los errores transitorios usan backoff acotado.
- El backlog se sincroniza antes de arrancar el thread y antes de habilitar las
  notificaciones. Si el listener no puede detenerse durante el cleanup, el lock
  se conserva hasta que termine el proceso para evitar dos consumidores.

## Estados y comandos

| Contexto | Comandos mutadores válidos |
|---|---|
| Ejecución normal | `/pause`, `/abort`, `/gate on|off` |
| Pausa pendiente o efectiva | `/resume`, `/abort`, `/gate on|off` |
| Pregunta de grill | `/answer`, `/done`, `/abort`, `/gate on|off` |
| Aprobación manual | `/approve`, `/reject [motivo]`, `/abort`, `/gate on|off` |
| Decisión tras cambios solicitados | `/retry [feedback]`, `/skip`, `/approve`, `/abort`, `/gate on|off` |

`/help`, `/status`, `/log`, `/verbose <1-50>`, los comandos de artefactos y `/ask` son
de lectura. `/ask` se rechaza cuando ya existe otra consulta o se ha solicitado
el aborto.

Semántica adicional:

- `/pause` queda pendiente hasta el siguiente checkpoint seguro. `/resume` puede
  cancelar esa solicitud o liberar una pausa efectiva.
- `/abort` se aplica inmediatamente durante una espera y al acabar la fase actual
  durante una llamada LLM.
- `/gate off` afecta a gates futuros y no decide una interacción ya abierta.
- `/approve` durante `review_decision` significa force-approve y debe indicarlo en
  el ACK.
- `/answer` y `/done` solo responden a la pregunta concreta publicada.
- `/comando@BotUsername` es sintaxis de Telegram; el sufijo nunca selecciona una
  misión.

## Entrega y replay

El transporte valida tanto el estado HTTP como `ok` en la respuesta. Los timeouts,
429 y 5xx son reintentables; 401, 403 y 409 son permanentes. Los mensajes son texto
plano UTF-8 y se fragmentan sin romper secuencias Unicode ni permitir que el índice
retroceda.

El siguiente `update_id` se persiste atómicamente por token antes de ejecutar el
comando, priorizando semántica *at-most-once*: ante un crash excepcional puede ser
necesario reenviar un comando, pero nunca se reproducirá automáticamente sobre una
misión posterior. En cada arranque, el offset parte del backlog observado en ese
momento y no del rango numérico histórico, porque Telegram puede cambiar dicho
rango después de periodos largos sin updates.

## `/ask`

`/ask` usa el cliente Anthropic y `AgentRunner` del harness, no el binario externo
`claude`. Solo admite una consulta simultánea, preguntas de hasta 2.000 caracteres,
8 turnos, 120 segundos, 1.200 tokens de salida y 12.000 caracteres por resultado de
herramienta. El prompt incluye un snapshot breve; los artefactos se leen bajo
demanda. Los 120 segundos forman un deadline compartido: cada request recibe solo
el tiempo restante, los retries internos del SDK se desactivan y `Grep` reduce su
propio timeout al presupuesto disponible. No se fuerza la terminación de una
operación síncrona ya iniciada en `Read`, `Glob` o `CodeGraph`; excepcionalmente
puede completar después del deadline, pero su resultado sigue siendo read-only.

`CodeGraph` abre `code_graph.db` en modo SQLite read-only, limita cada resultado a
200 filas y solo expone consultas. La telemetría registra modelo, turnos, duración,
tokens y resultado, nunca la pregunta ni la respuesta.

## Compatibilidad intencionadamente eliminada

- `/missions` y routing mediante `@tag`.
- `mission_tag` y `~/.harness/_missions.json` como estado activo.
- Entry point standalone de `telegram_listener.py`.
- Señales `_cmd_*`, `_waiting_approval` y `_waiting_notified`.
- Dependencia de Claude CLI para `/ask`.

El antiguo `_missions.json` se ignora y no se borra automáticamente.
