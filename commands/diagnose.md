Loop de diagnostico disciplinado para bugs dificiles y regresiones de rendimiento. No te saltes fases sin justificacion explicita.

Problema a diagnosticar: $ARGUMENTS

## Fase 1 — Construir un feedback loop

**Esta es la habilidad.** Todo lo demas es mecanico. Si tienes una senal de pass/fail rapida, determinista y ejecutable para el bug, encontraras la causa. Si no la tienes, ninguna cantidad de leer codigo te salvara.

Dedica esfuerzo desproporcionado aqui. **Se agresivo. Se creativo. No te rindas.**

Formas de construir un loop (intenta en este orden):

1. **Test que falla** en la costura mas cercana al bug (unit, integracion, e2e)
2. **Script bash** que ejecuta el codigo y compara output contra resultado esperado
3. **Invocacion CLI** con input de fixture, diff contra snapshot conocido
4. **Harness desechable** — subconjunto minimo del sistema que ejercita el code path del bug
5. **Biseccion** — si el bug aparecio entre dos estados conocidos, automatizar `git bisect run`

Itera sobre el loop: puedo hacerlo mas rapido? senal mas nitida? mas determinista?

**Si no puedes construir un loop:** para y dilo explicitamente. Lista lo que intentaste. Pide al usuario acceso al entorno, un artefacto capturado, o permiso para anadir instrumentacion temporal.

No avances a Fase 2 sin un loop.

## Fase 2 — Reproducir

Ejecuta el loop. Observa el bug aparecer. Confirma:

- [ ] El loop produce el fallo que **el usuario** describio — no otro fallo cercano
- [ ] El fallo es reproducible en multiples ejecuciones
- [ ] Has capturado el sintoma exacto (mensaje de error, output incorrecto, timing lento)

## Fase 3 — Hipotesis

Genera **3-5 hipotesis rankeadas** antes de testear ninguna. Cada hipotesis debe ser **falsificable**:

> "Si X es la causa, entonces cambiar Y hara desaparecer el bug / cambiar Z lo empeorara."

**Muestra la lista rankeada al usuario antes de testear.** Muchas veces tienen contexto de dominio que reordena instantaneamente.

## Fase 4 — Instrumentar

Cada sonda debe mapear a una prediccion de Fase 3. **Cambia una variable a la vez.**

Preferencia de herramientas:
1. Debugger / REPL si el entorno lo permite
2. Logs dirigidos en las fronteras que distinguen hipotesis
3. Nunca "logea todo y grepea"

**Etiqueta cada log de debug** con prefijo unico: `[DEBUG-xxxx]`. La limpieza se convierte en un solo grep.

## Fase 5 — Fix + test de regresion

1. Convierte el repro minimizado en un test que falla
2. Observa que falla
3. Aplica el fix
4. Observa que pasa
5. Re-ejecuta el feedback loop de Fase 1 contra el escenario original

## Fase 6 — Limpieza + post-mortem

- [ ] El repro original ya no reproduce (re-ejecuta loop de Fase 1)
- [ ] Test de regresion pasa
- [ ] Toda instrumentacion `[DEBUG-...]` eliminada
- [ ] Prototipos desechables eliminados

Pregunta final: **que habria prevenido este bug?**
