# Gobernanza de migración `main` -> HERO v2

- **Estado:** aceptada
- **Fecha:** 2026-08-29
- **Epic:** [Paridad controlada de HERO v2](main-develop-parity-epic.md)

## Regla de historia

`main` y `develop` no comparten ancestro. No son branches mergeables de una misma línea de desarrollo. Hasta que se apruebe una estrategia explícita de promoción:

- queda prohibido `git merge --allow-unrelated-histories` entre ambos árboles;
- queda prohibido crear un commit puente que tenga como padres ambas raíces;
- queda prohibido copiar en bloque el árbol v1 o aplicar una serie masiva de cherry-picks;
- queda prohibido forzar `main` o reescribir el tag histórico;
- las capacidades v1 se trasladan mediante contratos y tests en PRs descendientes de `develop`.

Git ya rechaza por defecto el merge no relacionado. La plantilla de PR hace visible la regla y `history-guard` comprueba que base y head tienen un merge-base antes de aceptar un PR dentro de la historia v2.

## Baselines congeladas

| Línea | Commit | Uso |
|---|---|---|
| HERO v1 | `ed1ff96290a16318d3717c67797b6e993bde82f5` | Evidencia histórica y pruebas de paridad |
| HERO v2 auditada | `7507caa3d1815d23940ebcc7c29e2dbc61ca2c6e` | Punto de partida del assessment |

El tag anotado `baseline/main-v1-ed1ff96` debe apuntar exactamente al commit v1. No se moverá. El nombre evita confundir la baseline con una release SemVer. Si aparece una corrección crítica en v1, recibirá otro tag y una decisión separada; no se altera la baseline.

## Contrato de PR

Todo PR del programa de paridad incluye:

```text
PARITY-ID: Rn | On | Ln
MAIN-EVIDENCE: commit/path/test
V2-CONTRACT: comportamiento observable
NEGATIVE-EVIDENCE: acción o fallo que ahora se rechaza
RESIDUAL-RISK: riesgo que permanece
```

Se permiten varios IDs solo cuando comparten una frontera indivisible. La conveniencia de editar los mismos archivos no es suficiente para agruparlos.

Antes de abrir el PR, el autor ejecuta:

```powershell
git merge-base origin/develop HEAD
```

El comando debe devolver un commit. No se usa `--allow-unrelated-histories`. Un PR ajeno al programa indica `PARITY-ID: N/A`, completa `NON-PARITY-REASON` y justifica que no modifica el contrato de sustitución.

## Qué significa portar una capacidad

Portar no significa igualar nombres de archivo. Un port válido:

1. identifica el invariante observable de v1;
2. define su lugar dentro de los puertos y autoridades v2;
3. añade una prueba que falla antes del cambio;
4. añade al menos un caso negativo cuando hay permisos, Git, procesos o estado persistente;
5. demuestra que snapshots, leases, receipts y Graph Lab siguen teniendo una única autoridad;
6. documenta diferencias deliberadas respecto a v1.

## Excepciones

Una excepción a esta política requiere:

- ADR dentro de `docs/hero-v2/`;
- impacto sobre rollback y trazabilidad;
- aprobación explícita del propietario;
- PR separado de la implementación funcional.

No existe excepción implícita por urgencia, tamaño del diff o porque Git permita forzar la operación.

## Enforcement

| Capa | Estado de Fase 0 |
|---|---|
| Decisión y baselines | Documentadas |
| Template de PR | Incorporado en `develop` |
| `history-guard` | Incorporado para futuros PRs basados en esta historia |
| Branch protection y required check | Pendiente de configuración remota; forma parte de R5 |
| Estrategia final de publicación v2 como `main` | Diferida hasta superar el gate de salida |

Mientras `main` sea la rama por defecto, GitHub toma de `main` las plantillas que ofrece al crear un PR. Por eso, la plantilla añadida a `develop` documenta el contrato y quedará activa automáticamente cuando la rama por defecto sea v2, pero todavía no aparece en la interfaz global. El workflow sí se evalúa en PRs cuya base sea `develop`; no protege PRs con base `main` hasta incorporar allí una regla equivalente sin mezclar las historias.

La promoción final puede ser un reemplazo controlado de la referencia, una nueva rama de integración o una migración de repositorio. Se decidirá cuando R1-R6 y los gates operativos estén cerrados; no se improvisa mediante un merge no relacionado.
