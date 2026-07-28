# Hardening minimo de alto impacto

**Estado:** P0 implementado; P1 pendiente

## Evidencia de cierre P0

- Implementacion separada en `1cfc05f` (Git), `040aa46` (CodeGraph) y
  `f7936c5` (fronteras de herramientas).
- Validacion local en Windows: `866` pruebas de `src/tests` y `111` de
  `benchmark`, todas correctas.
- CI [30353836169](https://github.com/mikelval82/hero-harness/actions/runs/30353836169):
  Ubuntu y Windows correctos.
- Auditoria final independiente de Git, CodeGraph y permisos: ningun defecto
  critico o alto pendiente.

Permanece un limite medio excepcional: si el filesystem impide simultaneamente
crear el marcador de invalidez y eliminar una base CodeGraph obsoleta, no puede
garantizarse fail-closed absoluto. No bloquea P0 bajo el supuesto fijado de un
workspace escribible. REVIEW conserva Bash como excepcion visible hasta P1.

## Objetivo

Reducir los riesgos mas importantes del runtime con el menor cambio razonable de
codigo. El estado objetivo de esta propuesta se limita a tres invariantes:

1. solo las fases de implementacion pueden usar `Write`/`Edit` sobre el proyecto
   target;
2. las fases analiticas conservan acceso estructural al code graph sin depender
   de una shell generica;
3. una mision no comienza ni continua si Git no esta en un estado verificable.

El cierre P0 no alcanza todavia todo ese estado objetivo: REVIEW conserva Bash
como excepcion transitoria hasta que el cierre P1 demuestre una validacion
independiente equivalente.

El objetivo no es convertir HERO en una sandbox de proposito general. El
implementer necesita ejecutar codigo del proyecto y, por tanto, el target debe
seguir considerandose confiable. La mejora consiste en reducir la superficie de
riesgo y hacer que el runtime cumpla las restricciones que ya declara.

## Decisiones P0 cerradas

Estas decisiones forman el gate de implementacion y no quedan abiertas a
interpretacion durante los tres commits de hardening:

| Frontera | Decision definitiva |
|---|---|
| Escritura | `PhaseConfig.allow_project_writes=False` por defecto. Solo `implement`, `implement_bursts` y `reimplement` pueden escribir en el target; las demas fases solo pueden escribir artefactos dentro del harness. |
| Code graph | La herramienta nativa conserva exactamente `find_nodes`, `dependencies`, `dependents`, `impact_analysis` y `dead_code`, con fallback recuperable a `Read`/`Glob`/`Grep`. |
| Bash analitico | `research`, `grill`, `structure`, `spec` y `plan` pierden Bash una vez migradas sus consultas al grafo estructurado. |
| REVIEW | Conserva Bash como excepcion P0 documentada, pero todos sus procesos hijos reciben el entorno sin credenciales de HERO. |
| Modos Git | `full`, `focused` y `hotfix` son mutantes. `explore`, `spec` y `spec-plan` no ejecutan ninguna operacion Git. |
| Resume | Un `--resume` mutante exige un workspace valido de ese proyecto y branch, HEAD adjunto y coincidencia exacta de branch; nunca hace checkout implicito. |

La implementacion se divide en tres commits independientes (`git`, `graph` y
`tools`) con pruebas deterministas por bloque y una unica auditoria global al
final. REVIEW conserva Bash; sustituirlo por una validacion mas estrecha queda
explicitamente en P1.

## Principios de la solucion

- **Cambio minimo:** reutilizar el registro de fases, el validador de paths y las
  funciones Git existentes.
- **Fail closed:** ante una duda sobre permisos, branch o commit, detener la
  mision en vez de continuar con un supuesto.
- **Sin nueva infraestructura:** no introducir contenedores, un motor de
  politicas, una DSL de permisos ni nuevas dependencias.
- **Preservar capacidad:** no retirar una herramienta hasta que exista una via
  equivalente para la funcion legitima que cubre actualmente.
- **Una regla por riesgo:** evitar listas extensas de excepciones dificiles de
  mantener.
- **Pruebas enfocadas:** validar los invariantes, no detalles internos de la
  implementacion.

## Fuera de alcance

Esta primera intervencion no incluye:

- aislamiento fuerte del implementer frente al sistema operativo o la red;
- soporte para ejecutar repositorios no confiables;
- una sandbox completa para Python, Git o procesos hijos;
- un sistema configurable de roles y permisos;
- rediseño del pipeline, de la memoria o de la arquitectura de prompts; solo se
  alinean con el runtime los contratos de herramientas afectados;
- correccion general del packaging, onboarding o benchmark;
- archivado de artefactos por tarea.

Estos temas pueden abordarse despues, pero no deben ampliar este cambio inicial.

## Resumen de cambios

| Prioridad | Cambio | Impacto esperado | Complejidad |
|---|---|---|---|
| P0 | Limitar escrituras por fase | Evita que research, spec, plan, review y report modifiquen el target mediante `Write`/`Edit` | Baja |
| P0 | Exponer `CodeGraph` como herramienta estructurada | Conserva el analisis de dependencias sin usar Bash como proxy | Baja-media |
| P0 | Retirar Bash de research, grill, structure, spec y plan despues de migrarlas | Reduce superficie de ejecucion sin perder orientacion estructural | Baja |
| P1 | Separar validacion de REVIEW de Bash generico | Permite retirar la ultima excepcion read-only sin degradar la auditoria | Media |
| P0 | Hacer Git fail-closed | Evita trabajar en la branch equivocada o incluir cambios previos del usuario | Baja-media |

## Cambio 1 — Limite real de escritura por fase

### Problema actual

Los agentes declaran artefactos `read_only` y `editable`, pero el runtime no
aplica esa distincion. `Write` y `Edit` validan que una ruta pertenezca al target
o al harness, pero no comprueban si la fase actual tiene permiso para escribir
en el target.

Como resultado, un reviewer, researcher o planner puede tecnicamente
sobrescribir codigo aunque su prompt lo prohiba.

### Solucion propuesta

Representar la capacidad de escritura de forma explicita en la configuracion de
cada fase:

```text
PhaseConfig.allow_project_writes = False  # valor seguro por defecto

implement | implement_bursts | reimplement
    -> allow_project_writes = True
```

`PhaseRunner` debe propagar ese booleano a `AgentRunner` y este a
`ToolExecutor`. Antes de despachar `Write` o `Edit`, el executor debe resolver
el `file_path` con la politica de paths existente y, cuando la capacidad sea
`False`, exigir que la ruta resuelta este dentro de `harness_dir`. El rechazo se
devuelve como `tool_result` para que quede registrado en la traza.

No debe inferirse el permiso a partir de `phase_name` ni parsearse nombres
decorados como `implement[T1]`. La configuracion canonica ya acompaña a la fase
y evita acoplar seguridad con formato de logging. Tampoco se necesita una clase
de permisos: un booleano con valor por defecto restrictivo cubre este
invariante.

### Modulos afectados

| Modulo | Cambio esperado |
|---|---|
| `src/core/context.py` | Añadir `allow_project_writes=False` a `PhaseConfig` y activarlo solo en las tres configuraciones de implementacion |
| `src/mission/phase_runner.py` | Propagar la capacidad tanto en fases normales como conversacionales |
| `src/agent/loop.py` | Entregar la capacidad al executor en cada llamada de herramienta |
| `src/agent/tools.py` | Aplicar la comprobacion comun antes de despachar `Write`/`Edit` |
| `src/agent/path_policy.py` | Reutilizar o extraer un helper pequeno para validar una escritura exclusiva en el harness |
| `src/tests/test_context.py`, `src/tests/test_mission.py` | Verificar el valor por defecto y su propagacion desde `PhaseRunner` |
| `src/tests/test_agent_loop.py`, `src/tests/test_tools.py` | Probar permitido/rechazado segun capacidad y destino |

No es necesario modificar `file_tools.py` si la restriccion se aplica en el
dispatcher comun y se sigue reutilizando su validacion normal de paths.

### Criterios de aceptacion

- Research puede escribir `brainstorm.md` dentro del harness.
- Research no puede escribir `src/app.py` en el target.
- Review puede escribir `audit.md` dentro del harness.
- Review no puede sobrescribir codigo o tests del target mediante `Write`/`Edit`.
- Implement y reimplement conservan su comportamiento actual.
- Una fase nueva queda sin escritura de proyecto si no declara la capacidad.
- Un path con `..`, symlink o forma relativa no puede evitar la comprobacion.

### Riesgo residual

Esta regla no protege frente a Bash. El cambio 2 elimina esa via en las fases
analiticas, pero REVIEW conserva una excepcion transitoria hasta el cierre P1.
Por tanto, la frontera completa frente a REVIEW no debe darse por resuelta en
el hardening P0. Tampoco se aisla al implementer, que conserva intencionadamente
capacidad de modificar y ejecutar el target.

## Cambio 2 — CodeGraph estructurado y reduccion progresiva de Bash

### Problema actual

Las fases `research`, `grill`, `structure`, `spec`, `plan` y `review` utilizan el
code graph para localizar simbolos, recorrer callers/callees y estimar impacto.
Hoy la unica via de consulta expuesta al modelo es Bash:

```text
python3 src/analysis/code_graph.py <command> [args]
```

Retirar Bash sin sustitucion dejaria construido `code_graph.db`, pero ningun
agente podria consultarlo. `Read`, `Glob` y `Grep` no son equivalentes para
recorrer dependencias transitivas y tampoco pueden leer una base SQLite como
herramienta semantica. Sustituir el grafo por esas herramientas degradaria una
capacidad real y contradiria los prompts actuales.

Al mismo tiempo, mantener Bash generico solo para consultar el grafo concede
mucho mas poder del necesario. La allowlist incluye interpretes y herramientas
extensibles como `python`, `git` y `awk`, ademas de comandos mutantes. Permitir
`python -c`, scripts del repositorio o procesos hijos hace que una validacion de
tokens no constituya una frontera de seguridad real.

El acceso CLI presenta ademas dos problemas funcionales:

- la ruta `src/analysis/code_graph.py` se resuelve desde el proyecto target;
  funciona cuando HERO se analiza a si mismo, pero no es portable a un target
  que no contenga ese script;
- el grafo se reconstruye antes de cada tarea, pero no necesariamente despues
  de implementar o reimplementar; REVIEW puede consultar relaciones obsoletas.

El grafo tiene limites que deben conservarse en su contrato: actualmente solo
indexa Python y el analisis estatico puede omitir wiring dinamico, reflexion,
plugins o llamadas resueltas en runtime. Debe ser la primera herramienta para
relaciones estructurales y complementarse con `Read`/`Glob`/`Grep`; no es una
fuente exclusiva de verdad.

### Solucion propuesta

No retirar Bash en el mismo cambio que crea su sustituto. Hacer una migracion
en dos pasos verificables.

#### Paso 2A — Herramienta read-only `CodeGraph`

Exponer una herramienta estructurada cuyo input no sea un comando shell:

```text
CodeGraph(
    action = find_nodes | dependencies | dependents | impact_analysis | dead_code,
    pattern = <substring literal, solo para find_nodes>,
    node = <id exacto, solo para recorridos>,
    limit = <1..200, opcional>
)
```

El handler debe abrir exclusivamente `$CLAUDE_HARNESS/code_graph.db` y devolver
texto acotado. El modelo no proporciona interprete, ruta del script, SQL ni
argumentos libres fuera del simbolo o patron de busqueda.

La herramienta no expone `build`. La construccion sigue siendo responsabilidad
del runtime. Antes de REVIEW y de cada re-review posterior a `reimplement`, el
runtime debe garantizar una reconstruccion incremental para que los resultados
representen el codigo auditado.

Si el grafo no existe, no puede actualizarse o no cubre el lenguaje del
proyecto, la herramienta devuelve un error recuperable y el agente continua con
`Read`/`Glob`/`Grep`.

Durante una etapa corta de compatibilidad, la CLI y `CodeGraph` pueden convivir.
La migracion se considera valida solo despues de comprobar que las operaciones
estructuradas producen resultados equivalentes a la CLI sobre un corpus pequeno.

#### Paso 2B — Matriz de capacidades despues de la migracion

```text
research | grill | structure | spec | plan
    -> Read, WriteHarness, Glob, Grep, CodeGraph

implement | implement_bursts | reimplement
    -> Read, Write, Edit, Glob, Grep, CodeGraph, Bash

review (estado transitorio)
    -> Read, WriteHarness, Glob, Grep, CodeGraph, Bash

review (estado objetivo)
    -> Read, WriteHarness, Glob, Grep, CodeGraph, RunValidation
```

`WriteHarness` representa la capacidad definida en el cambio 1: escribir
artefactos solo dentro del workspace del harness. No requiere una herramienta
nueva si se implementa mediante `allow_project_writes=False`.

`compact`, `consolidate` y `report` se mantienen sin Bash y sin CodeGraph salvo
que aparezca una necesidad concreta demostrada.

#### REVIEW es una excepcion separada

REVIEW no usa Bash solo para el code graph. Tambien debe ejecutar checks `DC*`,
tests y, si existe, `mission-validate.*`. Quitar Bash inmediatamente y pedirle
que confie solo en la evidencia del implementer reduciria la independencia de
la auditoria.

Por ello, REVIEW conserva Bash de forma transitoria despues de migrar sus
consultas a `CodeGraph`. La retirada posterior requiere una capacidad
`RunValidation` o ejecucion determinista desde el runtime que preserve, como
minimo:

- ejecucion de la validacion declarada por el target;
- ejecucion de los checks `DC*` autorizados sin aceptar un comando shell libre
  proporcionado en la llamada de herramienta;
- resultados y exit code sin resumir de forma enganosa;
- timeout y entorno reducido;
- evidencia asociada al check y disponible para el reviewer.

El origen de autorizacion debe definirse antes de implementar P1. Un comando
escrito por un agente en `spec.md` no se considera autorizado por ese hecho. Una
opcion minima es que `RunValidation` reciba un `check_id` y solo pueda resolverlo
contra entrypoints o comandos declarados por el proyecto en una configuracion
confiable. Si esa politica no puede cubrir los checks reales de REVIEW, Bash no
debe retirarse y el check debe quedar `NOT_RUN` con una limitacion explicita.

Hasta cerrar esa sustitucion no puede afirmarse que todas las fases read-only
carecen de shell ni que la frontera de escritura sea completa frente a REVIEW.

No se debe implementar una politica creciente de regex para permitir solamente
la CLI del grafo. Validar el `argv` completo, la ruta fija del script, el
interprete y cada operacion terminaria recreando una herramienta estructurada
detras de un campo `command`.

Como defensa barata adicional, el executor debe retirar del entorno de los
procesos hijos las credenciales propias del harness que el target no necesita:

- `ANTHROPIC_API_KEY`;
- `TELEGRAM_TOKEN`;
- `TELEGRAM_CHAT_ID`.

No se propone filtrar todas las variables del usuario porque podria romper los
tests del target. Esta limpieza protege solo credenciales controladas por HERO y
debe documentarse como reduccion de exposicion, no como sandbox completa.

### Modulos afectados

| Modulo | Cambio esperado |
|---|---|
| `src/agent/code_graph_tool.py` | Nueva herramienta read-only con operaciones enumeradas y salida acotada |
| `src/agent/tool_schema.py` | Registrar `CodeGraph` sin exponer shell ni SQL |
| `src/analysis/code_graph.py` | Extraer o reutilizar consultas para que CLI y herramienta compartan semantica |
| `src/core/context.py` | Anadir `CodeGraph` y `GRAPH_INSTRUCTIONS` a research, grill, structure, spec, plan, implement, implement_bursts, review y reimplement; retirar `Bash` de research, grill, structure, spec y plan solo despues de migrarlas; mantener REVIEW como excepcion transitoria |
| `src/agent/bash_executor.py` | Retirar del entorno hijo las tres credenciales propias de HERO antes de lanzar Bash |
| `src/mission/task_executor.py`, `src/mission/hitl.py` | Garantizar grafo actualizado antes de REVIEW y re-review, o delegar esa garantia a un helper comun del runtime |
| `agents/researcher.md`, `agents/griller.md`, `agents/structurer.md` | Sustituir invocaciones CLI por `CodeGraph`; conservar fallback con Read/Glob/Grep |
| `agents/specifier.md`, `agents/planner.md`, `agents/reviewer.md` | Sustituir invocaciones CLI por `CodeGraph` sin eliminar el analisis de impacto y callers |
| `prompts/graph-instructions.md` | Documentar el schema estructurado, limites y fallback; eliminar la ruta relativa `python3 src/analysis/code_graph.py` |
| `prompts/structure-prompt.md`, `prompts/reimplement-prompt.md` | Inyectar o referenciar las instrucciones de `CodeGraph`; hoy no reciben `GRAPH_INSTRUCTIONS` |
| `prompts/review-prompt.md` | Mantener validacion independiente; cambiarla solo cuando exista evidencia equivalente producida por `RunValidation` o el runtime |
| `src/tests/test_code_graph.py`, `src/tests/test_tools.py` | Verificar equivalencia de consultas, ausencia de `build`/SQL libre, salida acotada y errores recuperables |
| `src/tests/test_context.py`, `src/tests/test_prompt_contracts.py` | Verificar matriz de tools y ausencia de instrucciones CLI obsoletas despues de la migracion |

### Trade-off aceptado

El cambio incorpora una herramienta pequena en vez de limitarse a quitar una
capacidad. Se acepta porque evita una regresion funcional, corrige la ruta no
portable de la CLI y mejora la telemetria por operacion.

REVIEW conserva temporalmente una superficie mayor de la deseada. Es preferible
declarar ese riesgo que presentar como hardening una retirada de Bash que
impida ejecutar validaciones independientes. La frontera completa de REVIEW se
cierra en una iteracion posterior con `RunValidation` o ejecucion equivalente
desde el runtime.

### Criterios de aceptacion

- Research, grill, structure, spec y plan consultan el grafo sin Bash.
- Las cinco operaciones de `CodeGraph` producen resultados equivalentes a la
  CLI para los mismos inputs validos.
- `CodeGraph` no acepta `build`, SQL, rutas de base de datos, interpretes ni
  comandos arbitrarios.
- Un target externo que no contiene `src/analysis/code_graph.py` puede usar el
  grafo construido por HERO.
- La invocacion funciona en Windows y Linux sin depender del nombre `python3`.
- REVIEW consulta un grafo reconstruido despues de implement y reimplement.
- Si el grafo no esta disponible o no cubre el proyecto, cada agente continua
  con Read/Glob/Grep y registra la limitacion.
- Implement, implement bursts y reimplement siguen pudiendo ejecutar los tests
  del target.
- REVIEW conserva capacidad de validacion independiente durante la transicion;
  cualquier retirada de Bash exige pruebas de equivalencia de `RunValidation`.
- Los prompts y agentes no prometen una CLI o herramienta que el runtime no
  entrega.
- La documentacion no presenta la allowlist restante como una sandbox fuerte.
- Los procesos hijos no reciben credenciales propias de HERO y mantienen las
  demas variables necesarias para ejecutar tests normales.

### Riesgo residual

Implement y reimplement conservan ejecucion arbitraria con los permisos del
usuario. REVIEW tambien la conserva durante la transicion. HERO solo debe
ejecutarse sobre repositorios confiables y con el minimo de credenciales
externas disponible en el proceso padre.

`CodeGraph` reduce privilegios, pero no garantiza que el grafo sea completo o
semanticamente correcto. Sus resultados son evidencia estructural auxiliar y
deben contrastarse con codigo y tests.

## Cambio 3 — Preflight Git y propagacion de errores

### Problema actual

El flujo puede continuar aunque falle la creacion o el checkout de una branch.
Tampoco verifica que el worktree y el indice esten limpios antes de empezar.
`final_commit()` opera sobre todo el indice, por lo que podria incluir cambios
staged que ya pertenecian al usuario.

Ademas, la configuracion automatica de identidad puede modificar Git global,
una superficie mayor de la necesaria para una mision local.

### Solucion propuesta

Separar explicitamente tres caminos de arranque:

1. `explore`, `spec` y `spec-plan` no modifican Git: omiten identidad,
   creacion de `develop` y checkout de feature branch;
2. una mision nueva `full`, `focused` o `hotfix` comprueba que esta dentro de
   un repositorio y que `git status --porcelain` esta vacio antes de crear o
   reemplazar el workspace; despues configura la branch;
3. una mision mutante con `--resume` exige un workspace existente con
   `tasks.json` y que la branch actual coincida exactamente con la solicitada;
   no exige un worktree limpio y omite `ensure_develop()` y `setup_git()`.

El tercer camino es necesario porque una mision interrumpida puede dejar cambios
o tareas ya staged que forman parte de su propio estado. Forzar limpieza o hacer
otro checkout impediria reanudarla. Si `--resume` no encuentra un workspace
valido, debe fallar antes de borrar o crear nada, no convertirse silenciosamente
en una mision nueva.

En los caminos mutantes se debe validar por separado `user.name` y `user.email`.
Si se proporcionan `GIT_AUTHOR_NAME` y `GIT_AUTHOR_EMAIL`, se escriben solo en la
configuracion local del repositorio. Si falta cualquiera y Git no tiene una
identidad completa, la mision se detiene con instrucciones claras.

Todas las operaciones que cambian estado deben comprobar su `returncode` y
elevar un error con `stderr` concreto: checkout de `develop`, creacion y fallback
de checkout de la feature branch, `git add` y `git commit`. La consulta
`git diff --cached --quiet` debe distinguir entre "sin cambios" (`0`), "con
cambios" (`1`) y error (`>1`).

No se propone crear automaticamente worktrees en esta fase. Son una mejora
posible, pero amplian significativamente el flujo y la limpieza posterior.

### Modulos afectados

| Modulo | Cambio esperado |
|---|---|
| `src/core/git.py` | Añadir las consultas de preflight, validar ambos campos de identidad y propagar fallos de checkout/commit |
| `src/cli.py` | Seleccionar el camino segun modo y `--resume`, antes de ejecutar operaciones Git |
| `src/harness/harness_utils.py` | Hacer que un `--resume` sin workspace valido falle sin reemplazarlo |
| `src/harness/tasks.py` | Propagar fallos de `git add` y no anunciar como staged un archivo que fallo |
| `src/tests/test_git.py` | Cubrir worktree sucio, checkout fallido, identidad incompleta y commit fallido |
| `src/tests/test_mission.py`, `src/tests/test_mission_runner.py` | Verificar orden de arranque, modos sin Git y semantica de resume |

### Criterios de aceptacion

- Una mision mutante nueva no altera un repositorio con cambios previos del
  usuario.
- `explore`, `spec` y `spec-plan` no crean ni cambian branches.
- `--resume` solo continua sobre la branch y el workspace esperados, sin checkout
  adicional y conservando el estado de la mision.
- Un `--resume` invalido no reemplaza el workspace existente.
- Un checkout, `git add` o commit fallido produce salida no cero y no se informa
  como exito.
- HERO no modifica `~/.gitconfig`.
- La identidad se considera valida solo si existen nombre y email.
- Una mision sobre un repositorio limpio conserva el flujo existente.
- El preflight ocurre antes de borrar o recrear el workspace de la mision.

### Riesgos residuales

- Los cambios producidos por una tarea fallida pueden permanecer en el worktree
  durante la propia mision. Resolver rollback por tarea requiere un diseño
  transaccional separado.
- Al reanudar no es posible distinguir automaticamente cambios de la mision de
  cambios que el usuario haya añadido despues. `--resume` acepta el worktree
  actual como estado de la mision; aislar ambos origenes requeriria worktrees o
  commits transaccionales.
- El flujo actual puede fusionar una mision parcial. Cambiar esa politica debe
  tratarse como una decision funcional independiente.
- Los exit codes semanticos para `blocked`, `partial` y `not merged` merecen un
  cambio posterior si se quiere integrar HERO en automatizaciones.

## Orden de implementacion recomendado

### Patch 1A — Acceso estructurado al code graph

1. Registrar la herramienta `CodeGraph` con operaciones enumeradas.
2. Compartir semantica de consultas con la CLI existente.
3. Migrar prompts y agentes manteniendo ambas vias durante la compatibilidad.
4. Actualizar el grafo antes de REVIEW y re-review.
5. Probar equivalencia, portabilidad y fallback.

No retirar Bash de una fase hasta que sus consultas `CodeGraph` hayan sido
validadas. Este orden evita convertir el hardening en una regresion funcional.

### Patch 1B — Frontera de herramientas

1. Limite de escritura por fase.
2. Retirar Bash de research, grill, structure, spec y plan.
3. Mantener REVIEW como excepcion transitoria documentada.
4. Filtrar credenciales propias de HERO en procesos hijos.
5. Probar permisos y matriz de tools.

Los patches 1A y 1B deben ser revisables sin mezclar cambios Git.

### Patch 2 — Git fail-closed

1. Separacion de mision nueva, read-only y `--resume`.
2. Preflight de repositorio limpio para misiones nuevas mutantes.
3. Comprobacion de checkout, staging y commit.
4. Identidad completa y solo local.
5. Pruebas de fallo y orden de arranque.

### Patch 3 — Cierre de la excepcion REVIEW

1. Definir que fuentes confiables autorizan entrypoints y checks `DC*`; el
   contenido generado en `spec.md` no basta como autorizacion.
2. Definir el contrato minimo de `RunValidation` o ejecucion equivalente desde
   el runtime usando `check_id`, no un comando shell libre.
3. Demostrar equivalencia con los checks que REVIEW ejecuta actualmente.
4. Retirar Bash de REVIEW solo despues de esa validacion.

Este patch es P1 y puede desplegarse despues del hardening inicial. Hasta
entonces, la excepcion y su riesgo residual deben permanecer visibles.

Separar los patches reduce el riesgo de regresion y permite revertir cada
decision de forma independiente.

## Validacion minima

Ejecutar, como minimo:

```text
python -m pytest src/tests/test_context.py -q
python -m pytest src/tests/test_code_graph.py src/tests/test_tools.py -q
python -m pytest src/tests/test_agent_loop.py src/tests/test_prompt_contracts.py -q
python -m pytest src/tests/test_git.py -q
python -m pytest src/tests/test_mission.py src/tests/test_mission_runner.py -k "git or graph or setup or tool or resume or review" -q
```

Despues, ejecutar la suite completa en Windows y Linux. El cambio no se considera
cerrado solo porque los prompts expresen las nuevas restricciones: las pruebas
deben demostrar que el runtime rechaza las acciones prohibidas.

## Condicion de cierre

El hardening P0 se considera implementado cuando:

- research, grill, structure, spec y plan conservan acceso al code graph sin
  recibir Bash;
- `CodeGraph` funciona sobre targets externos en Windows y Linux, tiene salida
  acotada y no expone comandos, SQL ni construccion del grafo;
- REVIEW consulta un grafo actualizado despues de implement y reimplement;
- las fases read-only no pueden escribir en el target mediante `Write`/`Edit`;
- la excepcion Bash de REVIEW esta explicitamente documentada y su entorno no
  recibe credenciales propias de HERO;
- las fases de implementacion conservan su capacidad de trabajo y consulta del
  grafo;
- Git bloquea una mision mutante nueva sobre estado previo del usuario y
  propaga sus fallos;
- no se han introducido dependencias, motores de politicas ni capas de
  configuracion nuevas;
- la suite relevante pasa en Windows y Linux;
- la documentacion describe honestamente los riesgos residuales de implement y
  REVIEW.

El cierre P1 se alcanza cuando REVIEW puede ejecutar evidencia equivalente
mediante `RunValidation` o el runtime y deja de recibir Bash sin perder capacidad
de auditoria independiente.
