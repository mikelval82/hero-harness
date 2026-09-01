# L1 — Memoria de proyecto gobernada

L1 ofrece recuperación de notas de proyecto con fecha, provenance y revisión de
origen. El almacenamiento usa el canal de artefactos existente; no crea una
segunda autoridad de estado.

La lectura excluye conversación, mensajes, estado transitorio y telemetría. Los
valores que parezcan credenciales se redaccionan. `propose()` devuelve un diff
identificado y anclado al hash del valor anterior, pero no escribe ni aplica nada.
La aplicación futura requerirá aprobación humana, identidad estable, revocación y
registro de auditoría.

Estado: lectura y proposals locales implementados; no hay sincronización
persistentemente automática ni promoción sin aprobación.
