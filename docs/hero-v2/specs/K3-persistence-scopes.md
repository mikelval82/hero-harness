# K3 — Persistencia por ámbitos (spec ligera)

Deriva de la sección 6 de [hero-v2-grafo-vivo.md](../../hero-v2-grafo-vivo.md).

**Qué cambia.** `WorkspaceManager` deja de identificar proyectos solo por el basename sanitizado. El `project_id` se deriva de la ruta absoluta normalizada del repositorio (hash truncado); la clave de carpeta es `{nombre}-{project_id}` para que dos repos homónimos no compartan estado. Aparecen dos ámbitos bajo esa clave: `missions/<branch>` (efímero, se borra al reiniciar sin `--resume`) y `project/` (durable, jamás lo toca el setup de misión; K5 guardará ahí el baseline). El setup escribe un manifiesto `_mission.json` (project_id, ruta, rama, gate, timestamp), y la condición de reanudación pasa a ser la existencia del manifiesto — no la de `tasks.json` — de modo que una misión interrumpida durante research o grill es recuperable.

**Qué no cambia.** La firma de `setup()`, el `mission_tag` de presentación, la variable `CLAUDE_HARNESS`, el registry y el resto del CLI. No hay registro de proyectos con migraciones (diferido por debate).

**Cómo se verifica.** `tests/adapters/test_workspace.py`: misma ruta → mismo id; rutas distintas con mismo nombre → ids y workspaces distintos; resume con manifiesto pero sin `tasks.json` conserva el estado; reinicio sin resume borra la misión pero no el ámbito de proyecto; el manifiesto contiene ruta y rama.
