# Estrategia de review y eficiencia de tokens

**Estado:** propuesta

**Fecha:** 2026-07-26

## Veredicto

Sí existe margen importante para reducir tokens de revisión sin reducir los
tokens disponibles para implementar. Sin embargo, **no recomiendo sustituir
ahora todos los reviews por una única auditoría final**.

En el runtime actual, `REVIEW` no es solo una opinión sobre el código. También
controla la reimplementación, el HITL, el staging, el paso de la tarea a
`completed` y la compactación. Eliminarlo de cada tarea sin reemplazar esas
responsabilidades debilitaría el control del flujo y permitiría que un defecto
temprano condicionase varias tareas posteriores.

La estrategia con mejor relación entre ahorro, calidad y complejidad es:

1. medir y reducir primero el coste interno del review actual;
2. conservar feedback temprano, pero hacerlo progresivo: ligero para tareas `M`
   y completo para tareas `L`, reimplementadas o de riesgo alto;
3. añadir una comprobación final de integración que no repita todas las
   auditorías locales;
4. evaluar cualquier omisión de reviews en shadow mode antes de cambiar el
   comportamiento real.

No es honesto prometer "cero pérdida de capacidad" solo por reducir llamadas.
El objetivo verificable debe ser **no inferioridad de calidad**: menos tokens
con la misma detección de defectos bloqueantes, los mismos checks finales y sin
más retrabajo aguas abajo.

## Alcance y límites de la evidencia

Este análisis describe el código actual. No presupone que otras propuestas de
`docs/design/` estén implementadas.

Se revisaron:

- el routing `S/M/L` y el bucle de tareas;
- el reviewer, sus prompts, gates y selección de modelo;
- el ciclo HITL y de reimplementación;
- el cierre, commit, validación, reporte, memoria y mission cases;
- la telemetría disponible y una muestra histórica local.

### Muestra histórica disponible

En cuatro misiones legacy de `~/.harness/claude/`, fechadas entre el 14 y el 29
de mayo de 2026, se encontraron 17 registros de fase REVIEW. La normalización
tuvo que aceptar tanto `review[...]` como `PhaseName.REVIEW[...]`.

| Métrica REVIEW | Resultado observado |
|---|---:|
| Ejecuciones | 17 |
| Tokens totales | 7.874.106 |
| Media por review | 463.183 |
| Mediana | 441.624 |
| p90 | 593.023 |
| Rango | 240.867 - 839.284 |
| Proporción de input | 98,82 % |
| Turnos medios | 19,2 |
| Tiempo medio | 146,8 s |
| Peso de REVIEW en esas misiones | 14,4 % de los tokens |

Es evidencia direccional, no un benchmark actual:

- corresponde a un snapshot anterior del harness;
- no registra de forma fiable modelo, complejidad, intento ni veredicto;
- puede contener diferencias de prompts y runtime respecto a HEAD;
- solo cubre cuatro misiones y no permite estimar falsos positivos o negativos.

Por tanto, estos datos demuestran que el coste puede ser material, pero no
justifican prometer un porcentaje de ahorro futuro.

### Tamaño estático del contrato actual

En el snapshot actual:

| Archivo | Caracteres | Tokens aproximados con `chars / 4` |
|---|---:|---:|
| `agents/reviewer.md` | 11.981 | 2.996 |
| `prompts/review-prompt.md` | 4.452 | 1.113 |
| Total bruto | 16.433 | 4.109 |

Es una aproximación, no tokenización de la API. Además, excluye el crecimiento
por `spec.md`, `plan.md`, memoria, casos, skills, resultados de herramientas y
el historial de turnos. El propio `PhaseRunner` usa la misma heurística de
cuatro caracteres por token y solo emite un warning cuando el prompt supera
4.000 tokens; no aplica un límite.

El protocolo está parcialmente duplicado entre el agente y el prompt. Como el
loop vuelve a enviar sistema, mensajes y resultados de herramientas en turnos
sucesivos, una reducción del contexto fijo puede ahorrar input repetido sin
eliminar ninguna comprobación.

## Flujo real actual

| Complejidad | Pipeline | Review LLM |
|---|---|---|
| `S` | `implement` | No; se autoaprueba, stagea y compacta |
| `M` | `spec -> plan -> implement -> review` | Sí |
| `L` | `spec -> plan -> implement_bursts -> review` | Sí |

Por tanto, el harness ya aplica una primera optimización: las tareas `S` no
pagan review. El coste repetido se concentra en `M`, `L` y re-reviews.

Además, REVIEW siempre se enruta al tier `deep`, incluso para tareas `M`. El
cambio de modelo puede reducir coste monetario, pero no garantiza por sí solo
menos tokens. El ahorro de tokens debe venir principalmente de menos contexto,
menos turnos innecesarios y menos llamadas completas.

### Responsabilidades que hoy dependen de REVIEW

Después de producir `audit.md`, `HitlReviewer` decide:

- `APPROVED`: stage, `status=completed` y compactación;
- `MINOR_CHANGES`: reimplementación automática y aprobación sin un segundo
  review;
- `CHANGES_REQUESTED`: HITL, reimplementación, nuevo review y nueva decisión;
- rechazo, skip, force-approve o abort de la tarea.

Esto revela dos hechos distintos:

1. quitar REVIEW exige reemplazar también su función de control de estado;
2. el fast path de `MINOR_CHANGES` ya contiene una debilidad: modifica código y
   lo aprueba sin volver a comprobar el resultado.

### El cierre actual no es una auditoría final

El finalize actual hace `final_commit`, genera el reporte y después intenta el
merge, cuya validación es determinista mediante `mission-validate.*`.

El reporte resume estados y tokens, pero no compara el diff agregado con todas
las specs ni realiza una auditoría semántica de integración. Además,
`final_commit` ocurre antes de esa validación. Por ello, el cierre actual no
puede considerarse sustituto de los reviews por tarea.

## Evaluación crítica de una única auditoría final

### Ventajas reales

- Reduce el número nominal de llamadas de review cuando hay varias tareas.
- Observa el diff agregado y puede detectar incompatibilidades entre cambios
  localmente correctos.
- Evita repetir instrucciones, memoria y contexto compartido en cada tarea.
- Puede reservar el modelo más fuerte para una sola decisión global.

### Por qué no es un cambio aislado viable

| Limitación actual | Consecuencia de revisar solo al final |
|---|---|
| Al iniciar una tarea se eliminan `spec.md`, `plan.md`, `decisions.md`, `status.md` y `audit.md` anteriores | La auditoría final no conserva el contrato ni la evidencia completa de cada tarea |
| `tasks.json` no declara `depends_on`; solo expresa orden | No se puede saber qué tarea defectuosa invalida a cuáles posteriores |
| El loop continúa tras una tarea fallida salvo aborto de misión | Un error temprano puede propagarse por el mismo worktree |
| `completed` se asigna al aprobar/stagear cada tarea | Falta un estado intermedio equivalente a "implementada, aún no auditada" |
| `REIMPLEMENT` consume un único task id y los artefactos actuales | No existe reparación mission-wide ni restauración de la spec correcta |
| Los cambios son acumulativos y el commit es final | Un hallazgo tardío puede obligar a deshacer varias tareas coherentes con una base errónea |
| El gate de audit valida marcadores y formato | Concentrar toda la garantía en una llamada amplifica el impacto de un falso APPROVED |

También puede aparecer una falsa economía: una auditoría global recibe un
contexto mayor, necesita más lecturas y reenvía ese historial en cada turno. Si
repite todos los checks locales, puede consumir tantos tokens como los reviews
separados y ofrecer peor localización del fallo.

La comparación correcta es:

```text
T_actual = suma(review_local_M/L) + reimplementaciones + re-reviews

T_final_only = audit_global + reparación_global + re-audit_global
```

Contar llamadas sin medir sus tokens y el retrabajo no demuestra ahorro.

## Estrategia recomendada

### P0 — Medir bien antes de cambiar el routing

Usar la telemetría que ya existe, con un primer cambio pequeño:

1. emitir un único resultado por ejecución de fase, después del gate; hoy una
   fase puede registrar `success` y luego volver a contabilizar los mismos
   tokens como `gate_fail`;
2. normalizar nombres legacy como `review[...]` y `PhaseName.REVIEW[...]`;
3. mostrar en el reporte tokens y turnos por fase normalizada, incluido el
   porcentaje de REVIEW.

Esta fase no cambia calidad ni comportamiento y evita optimizar con una muestra
legacy poco representativa. La telemetría por turno, el tamaño de tool results,
las dimensiones de intento/veredicto y el shadow router pertenecen al
experimento P2, no a este parche inicial.

### P1 — Reducir tokens sin eliminar feedback temprano

Es el cambio mínimo recomendado para empezar:

1. **Una sola fuente de verdad del protocolo.** Mantener las reglas estables en
   `agents/reviewer.md`; dejar `review-prompt.md` como payload dinámico con tarea,
   artefactos y alcance. No repetir formato, taxonomía y reglas completas en
   ambos.
2. **Parada al escribir un audit finalizado.** Reutilizar la condición ya
   existente que detecta `audit.md` con `STATUS: DONE`, exigir además que pase
   el gate estructural y aplicarla al review no conversacional. El reviewer no
   debe seguir consumiendo turnos una vez entregado un artefacto válido.
3. **Evidencia acotada.** Pedir `Grep` y lecturas por rangos antes de leer
   archivos completos. No imponer todavía un truncado duro que pueda ocultar
   callers o requisitos; medir primero el tamaño de tool results.
4. **Validación global fuera del LLM.** Ejecutar `mission-validate.*` mediante el
   runtime antes del commit y pasar un resultado compacto al cierre. Los checks
   `DC*` específicos de tarea no deben eliminarse hasta que exista un ejecutor
   estructurado equivalente. Debe mantenerse también la validación previa al
   merge mientras `report` u otra fase posterior pueda escribir en el target;
   reutilizar un único resultado solo es seguro después de aplicar una frontera
   real de escritura por fase.
5. **Corregir `MINOR_CHANGES`.** Tras reimplementar, repetir al menos los checks
   afectados y un review ligero. Este punto puede consumir algunos tokens, pero
   cierra una pérdida de calidad existente y es condición previa para reducir
   reviews en otros lugares.

Si se aplica también la propuesta de retirar Bash del reviewer descrita en
`minimal_high_impact_hardening.md`, los comandos deterministas deben moverse al
runtime; no deben desaparecer silenciosamente.

### P2 — Review progresivo por riesgo

Después de obtener baseline y validar P1:

| Caso | Política propuesta |
|---|---|
| `S` | Hoy no tiene review; la propuesta añade antes un gate determinista real de checks y alcance del diff |
| `M` normal | Review ligero sobre spec, diff, resultados deterministas y riesgos |
| `M` con evidencia incompleta o señal de riesgo | Escalar a review completo |
| `L`, bursts, reimplementación o cambio crítico | Review completo |
| Misión con varias tareas | Auditoría final limitada a integración |

El review ligero debe responder solo a cuatro preguntas:

1. ¿pasan los criterios y checks bloqueantes?;
2. ¿el diff está dentro del alcance y archivos declarados?;
3. ¿hay un riesgo material, claim sin evidencia o `NOT_RUN`?;
4. ¿debe aprobarse o escalarse a review completo?

No necesita repetir en un caso limpio toda la narrativa de taxonomía,
gradientes y auditoría semántica. Si encuentra cualquier ambigüedad, falla de
forma conservadora y escala.

El tier `default` puede evaluarse para este fast path de tareas `M`; `deep` se
mantiene para `L`, escalados y re-reviews. Esto reduce coste, pero solo cuenta
como optimización de tokens si la medición confirma menos turnos/input.

### P3 — Auditoría final de integración

La auditoría final no debe volver a revisar cada requisito de cada tarea. Su
alcance debe limitarse a propiedades emergentes:

- compatibilidad entre APIs, callers, schemas y configuración modificados por
  tareas diferentes;
- resultado de la suite o validación global;
- coherencia del diff agregado con la intención de la misión;
- archivos fuera de alcance, duplicidad, regresiones o soluciones que se
  contradicen;
- riesgos no visibles dentro de una única spec.

Para minimizar llamadas, la última review existente puede recibir este alcance
adicional cuando la última tarea ya es `M` o `L`. Esa ampliación solo puede
auditar integración sobre el diff agregado y la validación final: no tiene
acceso implícito a specs o audits anteriores, porque hoy se eliminan al comenzar
la tarea siguiente. Si necesita revalidar evidencia local, primero debe
preservarse un paquete por tarea. Si la última tarea es `S` o no hubo review, se
ejecuta una fase `mission_review` explícita.

Debe ocurrir antes de `final_commit`, reporte, guardado de mission case,
sincronización de memoria y merge. Si modifica código mediante una reparación,
debe volver a ejecutar checks, stagear de nuevo y repetir la auditoría.

Ese orden presupone que `report` y las demás fases no implementadoras ya no
pueden escribir en el target. Mientras HEAD conserve esa capacidad, debe
mantenerse la validación posterior usada por el merge o repetirse después de
cualquier fase con escritura. La frontera de escritura propuesta en
`minimal_high_impact_hardening.md` es, por tanto, una dependencia de este cierre
ideal.

## Cuándo podría habilitarse `final-only`

No se recomienda como primer cambio. Requiere como mínimo:

1. introducir un estado `implemented` distinto de `completed`;
2. conservar en el harness un paquete por tarea con spec, plan, decisions,
   status, checks, archivos/diff y audit;
3. producir `mission-audit.md` sin sobrescribir los audits locales;
4. bloquear commit, reporte aprobado, memoria, mission case y merge mientras la
   auditoría final no esté aprobada;
5. disponer de reparación, re-stage, revalidación y re-audit antes de cualquier
   efecto final;
6. impedir que una fase posterior a la auditoría pueda modificar el target sin
   invalidar y repetir la validación.

Añadir `depends_on`, validar un DAG y bloquear solo los descendientes de una
tarea fallida mejoraría la reparación localizada, pero es una evolución
opcional, no un requisito mínimo para experimentar con `final-only`.

Esto es un rediseño del ciclo de estado y recuperación, no la eliminación de
una línea de `TASK_PIPELINES`.

## Módulos afectados

### P0/P1 — Cambio pequeño recomendado

| Módulo | Cambio propuesto |
|---|---|
| `src/mission/phase_runner.py` | Registrar una sola métrica tras el gate y activar parada temprana del review al escribir `audit.md` final |
| `src/harness/phase_logger.py`, `src/harness/telemetry.py` | Evitar doble conteo y agregar por fase normalizada |
| `src/mission/reporting.py` | Mostrar distribución de tokens y resultado determinista final |
| `agents/reviewer.md`, `prompts/review-prompt.md` | Eliminar duplicación y definir un fast path conciso |
| `src/mission/hitl.py` | Volver a verificar `MINOR_CHANGES` antes de aprobar |
| `src/core/git.py`, `src/mission/runner.py` | Ejecutar validación antes de commit sin retirar aún la defensa previa al merge |
| `src/tests/test_mission.py`, `src/tests/test_agent_loop.py` | Cubrir parada temprana y métrica única |
| `src/tests/test_telemetry.py`, `src/tests/test_phase_logger.py` | Cubrir normalización, agregación y ausencia de doble conteo |
| `src/tests/test_mission_runner.py`, `src/tests/test_git.py` | Cubrir re-review, validación y orden de finalize |
| `src/tests/test_prompt_contracts.py`, `src/tests/test_gate.py` | Mantener el contrato de audit tras compactar instrucciones |

### P2/P3 — Evolución posterior

| Módulo | Cambio propuesto |
|---|---|
| `src/core/context.py` | Representar alcance ligero/completo y, si se adopta, `mission_review` |
| `src/core/model_policy.py` | Routing `M=default`, `L/escalado=deep` basado en evidencia |
| `src/agent/loop.py` | Telemetría experimental por turno y tamaño de tool results |
| `src/mission/task_executor.py` | Seleccionar y registrar `light/full`; preservar evidencia antes de limpiar artefactos |
| `src/harness/tasks.py` | Estado provisional, dependencias y paquetes por tarea si se habilita defer/final-only |
| `agents/structurer.md`, `prompts/structure-prompt.md` | Declarar `depends_on` y señales de riesgo si se usa routing por dependencia |
| `src/core/gate.py` | Gate específico para review ligero y `mission-audit.md` |
| `src/mission/hitl.py`, `src/mission/runner.py` | Ejecutar auditoría de integración y su recuperación antes de cualquier efecto final |
| Nuevo `prompts/mission-review-prompt.md`, `prompts/report-full-prompt.md` | Definir el alcance de integración y reflejar su veredicto en el reporte |
| `src/harness/case_base.py` | Aceptar una misión solo con auditoría final aprobada, nunca por audit `UNKNOWN` |

## Validación de la propuesta

### Shadow mode

Durante varias misiones, mantener el review actual y registrar qué habría hecho
la nueva política. Comparar:

- tareas que el fast path habría aprobado frente a verdict real;
- `CHANGES_REQUESTED` o findings bloqueantes que se habrían omitido;
- tokens, turnos, tool-result chars, latencia y reimplementaciones;
- fallos descubiertos en tareas posteriores o en validación final;
- trabajo invalidado por un defecto temprano.

### Corpus controlado

Ejecutar la política actual y la propuesta sobre las mismas tareas congeladas,
incluyendo defectos sembrados:

- cambio incorrecto de una API consumida por una tarea posterior;
- migración o schema incompatible;
- test falsamente verde o excesivamente mockeado;
- archivo tocado fuera del alcance declarado;
- dos tareas localmente correctas pero incompatibles al integrarse;
- `MINOR_CHANGES` cuya corrección introduce una regresión.

### Criterios de aceptación

La política optimizada solo debe activarse si:

- reduce de forma material la mediana y p90 de tokens de REVIEW y el total por
  misión, no solo el número de llamadas;
- no omite ningún finding bloqueante del baseline o del corpus sembrado;
- no aumenta `NOT_RUN`, force-approve, fallos finales ni retrabajo downstream;
- mantiene los mismos resultados de tests y validación global;
- si se adopta routing por dependencias, una tarea defectuosa no libera sus
  descendientes;
- la auditoría final detecta incompatibilidades que los reviews locales no ven.

Como objetivo experimental, una reducción de al menos 30-35 % en mediana y p90
de tokens de review justificaría el cambio. Es un umbral de decisión propuesto,
no un resultado ya demostrado.

## Decisión recomendada

No eliminar ahora REVIEW de `M/L`. Primero implementar P0/P1, medir y compactar
el review. Después probar `M=light`, `L/riesgo=full` y una auditoría final de
integración estrecha.

Solo considerar `final-only` cuando existan evidencia preservada por tarea,
estado provisional, cierre fail-closed y reparación/re-audit global. Las
dependencias explícitas mejorarían la recuperación, pero no son condición para
un primer experimento. Hasta entonces, parece una optimización sencilla, pero
traslada el coste desde tokens visibles hacia errores acumulados y
reimplementación tardía.
