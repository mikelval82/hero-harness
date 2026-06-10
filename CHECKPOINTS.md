# CHECKPOINTS — Criterios de calidad universales

> Criterios objetivos que un agente revisor puede usar para decidir si el
> trabajo esta completo y correcto. Se evalua el destino, no el camino.

---

## C1 — Ciclo de desarrollo completo

- [ ] Existe `brainstorm.md` con analisis del problema y enfoque recomendado
- [ ] Existe `tasks.json` con tareas priorizadas y estado actualizado
- [ ] Existe `spec.md` con especificacion tecnica y criterios de aceptacion
- [ ] Existe `plan.md` con pasos de implementacion concretos
- [ ] Existe `decisions.md` con decisiones tecnicas justificadas

## C2 — Estado coherente

- [ ] `status.md` refleja el progreso real de la implementacion
- [ ] Cada paso del plan tiene estado (pendiente / en progreso / completado)
- [ ] `tasks.json` esta sincronizado con el trabajo actual

## C3 — Codigo limpio

- [ ] No hay `print()` sueltos para debug en codigo de produccion
- [ ] No hay TODOs sin contexto explicativo
- [ ] No hay secrets (.env, API keys) expuestos en el codigo
- [ ] El codigo sigue los patrones existentes del proyecto

## C4 — Verificacion funcional

- [ ] Tests existen para la funcionalidad nueva (cuando aplica)
- [ ] Los tests pasan al ejecutarlos
- [ ] No se han introducido regresiones en funcionalidad existente

## C5 — TDD y calidad de tests

- [ ] Si hay tests, siguen disciplina TDD (vertical slices, no horizontal)
- [ ] Tests verifican comportamiento a traves de interfaces publicas, no detalles de implementacion
- [ ] Tests sobrevivirian un refactor interno sin cambios

## C6 — Lenguaje compartido

- [ ] El codigo y documentacion usan terminologia consistente
- [ ] Si se introdujeron nuevos conceptos, estan definidos o son auto-explicativos

## C7 — Cierre limpio

- [ ] `status.md` actualizado con estado final
- [ ] `audit.md` existe con veredicto del reviewer
- [ ] No hay archivos temporales sueltos en el proyecto

---

**Como usar este archivo:** el agente `reviewer` (paso 6 de su protocolo) lee
este archivo cuando esta disponible, recorre los checkpoints relevantes, marca
`[x]` los que se cumplen, `[ ]` los que no, y emite su veredicto en
`$CLAUDE_HARNESS/audit.md`.
