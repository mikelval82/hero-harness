# O5 - Coste trazable y token budget

## Contrato

Cada resultado de fase genera un `cost_record` con `served_provider`,
`served_model`, tokens de entrada/salida, `catalog_version` y coste. El cálculo
usa exclusivamente el modelo servido; si éste o su tarifa falta del catálogo,
`estimated_usd` es `null` y `known` es `false`, nunca cero.

El catálogo es un artefacto versionado del runtime, inmutable durante una
misión. Sus tarifas se expresan por millón de tokens de entrada/salida y no se
copian desde `main` sin revisión explícita.

`TOKEN_BUDGET` es opt-in. Se evalúa en el safe point anterior a iniciar una
nueva fase, tras sumar resultados ya observados. Al excederse bloquea antes de
una nueva llamada de proveedor; no interrumpe una llamada ni borra artefactos.

## Aceptación

1. El coste conocido usa sólo `served_model` y no doble cuenta turnos.
2. Modelo o tarifa desconocidos producen `known=false` y coste `null`.
3. El agregado conserva tokens aunque haya costes desconocidos.
4. El budget bloquea únicamente en el safe point y es reproducible.
5. Tests locales no requieren credenciales ni precios consultados en red.
