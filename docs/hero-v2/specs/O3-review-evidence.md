# O3 — Review con evidencia y taxonomía

Review produce dos artefactos distintos. `audit.md` conserva la explicación
humana y el veredicto. `review-evidence.json` es el contrato tipado que enlaza
cada claim con referencias concretas, registra los checks obligatorios de
hardcoding, special-casing y scope, y clasifica cualquier fallo con su etapa de
recuperabilidad.

El gate no aprueba un audit `APPROVED` si alguno de esos checks falla/no se
ejecuta, queda un claim sin soporte o existe un fallo pendiente. Una revisión no
aprobada debe declarar al menos un fallo tipado. Después, y solo después de que
el `PythonContractVerifier` independiente pase, el runtime escribe
`review-receipt.json`. Este receipt fija hashes de audit, contrato, verificador
y receipts de validación, además del scope declarado y cambios observados.

El receipt no sustituye al verificador estructural: una implementación puede
tener buen audit y evidencia de review, pero no se completa si el contrato
estructural falla.
