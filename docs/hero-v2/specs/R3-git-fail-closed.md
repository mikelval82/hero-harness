# R3 — Git transaccional y fail-closed

## Objetivo

Una misión que puede modificar un proyecto no debe crear o borrar su workspace,
cambiar de rama ni atribuir cambios a HERO hasta comprobar que el repositorio y
su identidad satisfacen el contrato.

## Contrato v2

Antes de crear el workspace, las misiones `full`, `focused` y `hotfix` validan
que `project_dir` es la raíz de un repositorio Git, que la rama supera
`git check-ref-format --branch` y que hay una identidad Git completa de ámbito
local. `GIT_AUTHOR_NAME` y `GIT_AUTHOR_EMAIL` se aceptan solo como un par y se
escriben mediante `git config --local`.

Una misión nueva exige worktree limpio por defecto. `--allow-dirty` es una
aceptación explícita: toma un receipt `dirty-baseline.json` con path, estado y
SHA-256 de cada cambio previo, y el servicio rechaza posteriormente stagear
esos paths. Así no se atribuyen ni se incluyen en el commit final de la misión.

`--resume` no hace checkout ni crea una misión nueva. Requiere una rama adjunta
que coincida exactamente y un `_mission.json` existente cuyo proyecto y rama
sean los esperados. Una rama distinta, un HEAD detached, un manifiesto ausente o
un manifiesto alterado bloquean antes de tocar el workspace.

Los modos `plan` y `explore` no ejecutan preflight mutador, checkout ni setup
de rama: mantienen su naturaleza sin merge.

## Criterios de aceptación

- Preflight ocurre antes de `WorkspaceManager.setup()` y antes de cualquier
  checkout.
- Branch inválida, repo ajeno/no Git, identidad incompleta o worktree sucio sin
  opt-in fallan cerrados.
- Baseline sucia autorizada queda registrada y sus paths no se pueden stagear.
- Resume exige workspace, manifiesto y rama exactos; nunca degrada a misión
  nueva.
- Errores de checkout, stage, commit y merge se propagan como excepciones; no
  se convierten en éxito.

## Límite deliberado

R3 no aísla el worktree a nivel de sistema operativo ni determina qué cambios
posteriores sobre un path previamente sucio pertenecen semánticamente al
usuario. Los prohíbe del stage automático para no atribuirlos erróneamente.
R5 debe añadir la evidencia CI multiplataforma y la política de protección de
ramas.
