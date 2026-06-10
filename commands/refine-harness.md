Genera una propuesta offline de mejora del harness desde fallos recurrentes.

Input opcional: $ARGUMENTS

## Proceso

1. Identifica el workspace de harness:
   - Si `$ARGUMENTS` contiene una ruta, usala como harness.
   - Si no, usa `$CLAUDE_HARNESS`.

2. Genera una propuesta ejecutando:

   ```bash
   python src/harness/harness_utils.py refiner-proposal "$CLAUDE_HARNESS"
   ```

3. Lee `refiner-proposal.md` y presenta al usuario:
   - firmas de fallo recurrentes detectadas;
   - cambios propuestos;
   - artefactos objetivo;
   - riesgos;
   - decision humana requerida.

## Reglas

- No edites prompts, agentes, codigo, tests, memoria, casos ni skills.
- No apliques parches.
- Si la propuesta parece razonable, pide aprobacion humana antes de convertirla en una tarea normal del backlog.
- Si no hay evidencia recurrente, conserva el no-change proposal como registro.
