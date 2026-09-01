# Runbook de promoción controlada de v2

## Estado de corte

- `main` histórico: `ed1ff96290a16318d3717c67797b6e993bde82f5`
- `develop` candidato actual: `478023994852f195440ea108e1d752391079a903`
- Baseline de rollback: tag `baseline/main-v1-ed1ff96`

## Gates previos

1. Ejecutar la suite completa y los checks requeridos de Ubuntu y Windows sobre
   el SHA candidato.
2. Ejecutar y archivar un smoke autorizado Graph Lab → worker → control plane.
3. Ejecutar al menos un smoke autenticado de proveedor; Anthropic y DeepSeek se
   mantienen `NOT_RUN` hasta disponer de red y credenciales autorizadas.
4. Revisar la release note: capacidades fusionadas, experimentales, retiradas y
   riesgos residuales.

## Procedimiento

Crear una rama de integración desde `main`, aplicar el contenido de `develop` sin
`--allow-unrelated-histories`, validar los gates sobre el resultado y abrir un PR
con revisión humana. No hacer force-push ni borrar `main`; la protección actual lo
impide. Si el PR no es aceptable, cerrar sin modificar la rama pública.

## Rollback

El rollback lógico es volver a `baseline/main-v1-ed1ff96` o al último SHA de
`main` aprobado. La operación debe conservar ambos refs y documentar el motivo;
no se borra el tag histórico.

## Decisión actual

La promoción está **bloqueada** hasta completar los smokes `NOT_RUN`. Los checks
locales/CI de código no prueban autenticación, TLS, cuotas ni el navegador real.
