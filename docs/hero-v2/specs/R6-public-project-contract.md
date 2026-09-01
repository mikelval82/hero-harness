# R6 — Contrato de proyecto público

## Contrato v2

La distribución se llama `hero-harness` y conserva `mission_orchestrator` como
módulo Python y namespace de los entry points. `pyproject.toml`, README,
licencia, enlaces públicos y classifiers describen la misma identidad.

El repositorio publica una licencia MIT, guía de contribución v2 y plantillas
de PR e issues que piden contratos, evidencia y ausencia de secretos. La plantilla
`.env.example` enumera sólo nombres de configuración y valores públicos; queda
versionada mediante la excepción explícita a la regla de ignore de `.env.*`.

## Evidencia exigida

- Construir e instalar el paquete desde el árbol limpio y comprobar sus entry points.
- Ejecutar la suite completa y los checks CI de Ubuntu y Windows sobre el SHA de la PR.
- Verificar que `.env.example` está rastreado y que no contiene credenciales.
- Distinguir en README los contratos locales, CI sin secretos y el smoke autenticado.

## Límite deliberado

R6 no ejecuta ni habilita un provider. El smoke autenticado sigue requiriendo
aprobación explícita y una red/credenciales autorizadas; por tanto no transforma
la compatibilidad DeepSeek o Anthropic en una afirmación E2E.
