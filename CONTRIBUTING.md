# Contribuir a HERO Harness v2

Gracias por mejorar HERO Harness. `develop` es la línea v2 y no se mezcla de
forma directa con la historia v1 de `main`; cada cambio se propone mediante una
PR pequeña, revisable y con evidencia proporcional al riesgo.

## Preparar el entorno

Usa Python 3.12 o posterior. Para las pruebas de contrato no se necesita una
clave de proveedor:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[anthropic,deepseek]"
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Consulta [`.env.example`](.env.example) antes de configurar un provider. Las
claves reales viven sólo en el entorno local o en secretos aprobados; no se
incluyen en issues, PRs, fixtures ni logs.

## Proponer un cambio

1. Crea una rama desde `develop` y limita el cambio a un objetivo verificable.
2. Actualiza tests y documentación cuando cambie un contrato observable.
3. Ejecuta la suite completa y explica cualquier evidencia que no pueda
   reproducirse localmente.
4. Abre una PR usando la plantilla. Si afecta al roadmap de paridad, declara el
   `PARITY-ID`, la evidencia v1, el contrato v2, una evidencia negativa y el
   riesgo residual.

Los checks de Ubuntu y Windows son obligatorios. Un mock o un check local no
prueba un proveedor real; los smokes autenticados requieren aprobación explícita
y deben declarar su alcance y resultado.

## Diseño y seguridad

Conserva la separación entre dominio, aplicación, puertos y adapters. No
introduzcas una segunda autoridad de estado ni ejecución de shell controlada por
un modelo. Cualquier cambio que afecte a credenciales, procesos, Git, Telegram o
contratos de Graph Lab debe incluir una prueba de rechazo o bloqueo de la ruta
insegura.

Al contribuir aceptas que tus aportaciones se publiquen bajo la [licencia MIT](LICENSE).
