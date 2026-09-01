## Resultado

Describe qué comportamiento observable cambia y por qué.

## Contrato de paridad

- `PARITY-ID:` <!-- R1-R6, O1-O8, L1-L4; o N/A con justificación -->
- `NON-PARITY-REASON:` <!-- obligatorio únicamente cuando PARITY-ID sea N/A -->
- `MAIN-EVIDENCE:` <!-- commit/path/test de main, si aplica -->
- `V2-CONTRACT:` <!-- invariante implementado detrás de la arquitectura v2 -->
- `NEGATIVE-EVIDENCE:` <!-- acción/fallo que ahora se rechaza o bloquea -->
- `RESIDUAL-RISK:`

## Historia Git

- [ ] `git merge-base origin/<base> HEAD` devuelve un commit.
- [ ] No se usó `--allow-unrelated-histories` ni se creó un commit puente entre v1 y v2.
- [ ] No se copió el runtime v1 como una segunda pila o autoridad de estado.

## Verificación

- [ ] Añadí o actualicé tests proporcionales al riesgo.
- [ ] Ejecuté `mission-validate` para este checkout.
- [ ] Registré evidencia E2E cuando el cambio cruza browser, proceso o proveedor.
- [ ] Distinguí mocks/checks locales de compatibilidad real.
- [ ] Actualicé el [epic de paridad](../docs/hero-v2/main-develop-parity-epic.md) si cierro o cambio un ID.

## Rollback

Explica cómo revertir el cambio sin reintroducir la implementación v1 ni perder estado autoral.
