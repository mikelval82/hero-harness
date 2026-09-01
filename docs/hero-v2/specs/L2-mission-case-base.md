# L2 — Mission case base

El case base solo recupera misiones terminales verificadas. Cada entrada debe
estar anclada a `snapshot_id`, `contract_id`, `commit_sha` y una lista de receipts;
los paths absolutos y la conversación no forman parte del schema.

El schema es `l2-v1`, con score, fecha de verificación y revisión de origen. La
consulta ignora entradas incompletas, no verificadas o tombstoned y ordena por
score. `revalidate()` compara la revisión de la entrada con el código actual.
`tombstone()` genera una revocación auditable, pero esta primera entrega no
persiste ni aplica cambios automáticamente.
