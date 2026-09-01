# A4 — Comandos por HTTP

Spec ligera (la infraestructura y la seguridad vienen de A3; esto añade una ruta y reutiliza el gate existente). Anillo 1, tarea A4. Referencia: visión §11 ("entrada de interacciones tipadas" como puerto; el humano llega por Web/stdin/Telegram al mismo gate).

## 1. Problema

El servidor de A3 es de solo lectura: para aprobar un mapa hay que volver a la terminal o a Telegram. La UI (A5) necesita mutaciones — pero sin duplicar ni un milímetro de lógica de comandos.

## 2. Contrato

- `POST /api/command` con cuerpo JSON `{"text": "<comando>"}` — la misma sintaxis que stdin/Telegram (`/approve`, `/reject <razón>`, `/abort <razón>`, `/retry <feedback>`, texto plano = respuesta conversacional).
- El texto pasa por **`parse_control_command`** (el gate tipado único) y el `Command` resultante se publica en el **mismo `CommandBus`** que consume el orquestador. Cero lógica nueva de interpretación.
- Respuesta `200 {"accepted": true, "kind": "<kind>"}`; texto vacío o no parseable → `400`; cuerpo JSON inválido → `400`.
- `MissionWebServer` gana el parámetro opcional `commands: CommandBus | None`; sin bus (servidor de solo lectura) → `503`.
- Seguridad idéntica a A3 (token + origen) aplicada también a POST.
- `cli.py`: pasa el bus al servidor cuando `--web`.

## 3. Criterios de aceptación

- **C1** `POST /api/command {"text": "/approve"}` → `200`, `kind="approve"`, y el bus contiene `Command(APPROVE)`.
- **C2** `/reject too big` conserva la razón en el comando publicado.
- **C3** POST sin token → `401`; con `Origin` ajeno → `403`; nada llega al bus.
- **C4** Cuerpo inválido o texto vacío → `400`; nada llega al bus.
- **C5** Texto plano sin `/` se publica como `ANSWER` (respuesta conversacional al griller).
- **C6** Servidor construido sin bus → `503`.
- **C7** La suite previa (113 tests) permanece verde.
