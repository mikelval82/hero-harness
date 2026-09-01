# O6 - Modos parciales

`spec-plan` es un alias de entrada de `plan` y no crea un pipeline paralelo.
`spec` es spec-only: ejecuta `SPEC` y `REPORT_PLAN`, no entra en el task loop y
no permite merge ni mutaciones de proyecto/Git. `full`, `focused`, `hotfix` y
`explore` conservan sus pipelines canónicos existentes.

La aceptación exige que cada alias resuelva al enum canónico, que los modos
parciales no muten el proyecto y que la matriz de pipelines quede cubierta por
tests de dominio y de entry points.
