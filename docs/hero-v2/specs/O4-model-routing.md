# O4 - Routing provider-neutral de modelos

## Objetivo

Seleccionar de forma determinista el proveedor y modelo para cada fase sin
introducir una segunda autoridad de ejecucion. La politica es una dependencia
del runtime: los adapters solo ejecutan la seleccion que reciben y reportan lo
que el proveedor sirvio realmente.

## Limites

O4 no incorpora precios, agregacion de coste ni enforcement de presupuesto:
esos pertenecen a O5. Tampoco habilita un proveedor nuevo ni convierte un
override de entorno en una credencial.

## Contrato

`ModelPolicyPort.select` recibe `phase`, `complexity`, `retry_count` y las
capacidades provider/modelo configuradas en el runtime. Devuelve una
`ModelSelection` inmutable con:

- `requested_provider`, `requested_model` y `tier` (`cheap`, `default`,
  `deep` o `forced`);
- una `reason` estable y apta para telemetria;
- una `policy_version` para que la decision sea reproducible.

La politica base usa `cheap` para `compact`, `consolidate`, `report` y
`report_plan`; `deep` para `grill`, `review` y `reimplement`; y `default` para
el resto. Una tarea de complejidad `L` o cualquier `retry_count > 0` escala a
`deep`. Un provider/modelo indicado explicitamente por CLI o configuracion es
un override `forced` y prevalece sobre las reglas de tier.

La politica no cambia de proveedor por su cuenta. Solo puede devolver una
combinacion incluida en `provider_capabilities`; una seleccion imposible es un
error de configuracion fail-closed antes de llamar a red.

Cada invocacion emite un evento sin contenido de prompt/respuesta que separa
la identidad solicitada de `served_provider`/`served_model`. Si el SDK no
declara el modelo servido, el campo queda `unknown`, nunca se sustituye por el
modelo solicitado.

## Outcome provider-neutral

Los adapters clasifican cada respuesta como `completed`, `tool_use`,
`truncated`, `refused`, `paused`, `malformed`, `transport_error` o
`quota_error`. Solo `completed` y un `tool_use` coherente pueden continuar el
loop. `truncated`, `refused`, `paused` y `malformed` bloquean la fase con una
razon explicita; no se convierten en un resultado textual parcial. Los errores
de transporte y cuota conservan las rutas de bloqueo ya existentes.

## Criterios de aceptacion

1. La misma entrada de politica produce la misma seleccion y razon.
2. Fases cheap/deep, complejidad `L`, retry y override tienen tests positivos.
3. Un provider/modelo no declarado se rechaza antes del adapter.
4. Los eventos contienen identidad solicitada y servida, tier, razon y outcome,
   sin prompt ni texto de respuesta.
5. Anthropic y DeepSeek rechazan de forma fail-closed truncacion, rechazo,
   pausa, payload sin respuesta y finish/stop reason desconocido.
6. La seleccion forzada mantiene la reproducibilidad y no realiza fallback
   silencioso entre proveedores.
7. La suite local distingue estos contratos de un smoke autenticado; ningun
   test requiere una credencial de proveedor.

## Rollback

Revertir el commit O4 restaura la seleccion unica de `build_runtime`. No se
tocan credenciales, artefactos de mision ni precios de O5.
