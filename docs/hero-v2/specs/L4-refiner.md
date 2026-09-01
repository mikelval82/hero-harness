# L4 — Refiner post-misión

El refiner consume únicamente casos verificados y produce hipótesis sobre
observaciones recurrentes. Requiere un corpus mínimo de dos casos y conserva los
IDs que explican cada coincidencia; dos coincidencias léxicas no se presentan como
causalidad.

El resultado es siempre `RefinementProposal` con `approval_required=true` y
`auto_apply=false`. No puede editar prompts, agentes, tests, memoria ni skills.
La aprobación humana debe convertir una propuesta aceptada en una tarea normal.
