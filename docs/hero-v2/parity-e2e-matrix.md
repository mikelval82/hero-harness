# Matriz de evidencia E2E y paridad

Esta matriz separa pruebas locales, CI y smokes autenticados. Un estado `NOT_RUN`
no se interpreta como compatibilidad demostrada.

| Escenario | Evidencia | Estado | Límite |
|---|---|---|---|
| Control plane local: snapshot, contratos y documentos | `tests/adapters/test_control_http_server.py` | PASS local + CI | No usa proveedor real |
| Grafo factual read-only | `tests/adapters/test_code_graph.py` | PASS local + CI | SQLite observado de fixture |
| Flujo de tareas y contrato/verificación | `tests/application/test_plan_pipeline.py`, `test_contract_execution.py` | PASS local + CI | No es un smoke Graph Lab desplegado |
| `/ask` positivo/negativo | `tests/application/test_code_questions.py` y autoridad de herramientas | PASS local + CI | Agente simulado; no proveedor autenticado |
| Modos `spec` y `spec-plan` | `tests/domain/test_domain_contracts.py`, `tests/test_worker.py` | PASS local + CI | No prueba integración UI |
| Anthropic autenticado | smoke separado | NOT_RUN | Requiere credencial y red autorizadas |
| DeepSeek autenticado | smoke separado | NOT_RUN | TLS/red corporativa pendiente |
| Graph Lab -> worker -> control plane real | smoke E2E separado | NOT_RUN | Requiere entorno autorizado y artefactos de proyecto |

## Criterio de promoción

Solo se puede cerrar la paridad cuando cada escenario necesario tenga evidencia
reproducible en su entorno declarado, los smokes de proveedor estén ejecutados o
se retiren explícitamente del alcance, y los casos negativos sigan bloqueando el
éxito. La suite local completa observada en esta línea es `241 passed`; no sustituye
los smokes `NOT_RUN`.
