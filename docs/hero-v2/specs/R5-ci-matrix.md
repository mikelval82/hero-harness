# R5 — Señal CI multiplataforma

## Contrato v2

La workflow `CI` se ejecuta en los pull requests y pushes que afectan a
`develop` o `main`, con Python 3.12 sobre Ubuntu y Windows. Instala el paquete
con los extras de proveedor, ejecuta `pip check`, importa el módulo, comprueba
los tres entry points publicados y termina con la suite completa `unittest`.

El smoke autenticado está separado: solo se puede lanzar manualmente y exige un
environment de GitHub aprobado. No lee secretos ni contacta proveedores desde
la CI ordinaria. Mientras no haya un entorno aprobado y conectividad de
proveedor, su resultado honesto es `NOT_RUN`, no una señal verde sintética.

Las ramas deben requerir los checks `test (ubuntu-latest)` y
`test (windows-latest)` antes de mergear. Esta regla se aplica mediante la API
de GitHub después de que los checks existan en el SHA; si la credencial no tiene
permisos de administración, R5 deja el workflow listo pero reporta esa
limitación en vez de afirmar que la protección está activa.
