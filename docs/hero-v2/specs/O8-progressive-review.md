# O8 — Review progresivo (experimental)

O8 define únicamente un experimento *shadow*. No cambia el reviewer de
producción ni permite promoción automática.

El corpus se compone de casos emparejados por `case_id`, con baseline de review
completo congelado y una observación progresiva. Debe incluir defectos sembrados
de API, schema, hardcoding, scope e integración entre tareas. El evaluador calcula
mediana y p90 de tokens y turnos, findings bloqueantes omitidos y retrabajo
downstream.

La activación solo es elegible cuando no se omite ningún finding bloqueante, no
existe retrabajo downstream y el consumo total de tokens no supera el baseline.
La decisión sigue siendo humana y el resultado se conserva como evidencia; una
evaluación incompleta o con corpus desalineado bloquea la promoción.

Estado actual: experimento offline implementado; no está anunciado como estrategia
de review soportada en producción.
