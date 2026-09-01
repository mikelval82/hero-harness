# O7 — `/ask` read-only

## Purpose

Expose a bounded asynchronous question surface over the existing control plane. It
is an inspection aid, not a second mission runtime and not a mutation channel.

## Contract

- `POST /api/v1/ask` accepts `{ "question": string }` and returns `202` with an
  `operation_id`.
- `GET /api/v1/ask/{operation_id}` returns `running`, `completed`, `busy`,
  `timeout`, `max_turns`, or `unavailable`.
- Questions are limited to 2,000 characters; answers to 3,500 characters.
- One question may execute per mission. The agent receives at most 8 turns and
  120 seconds. Tool authority is exactly `Read`, `Glob`, `Grep`, and `CodeGraph`;
  it has no project writes, harness mutations, `Edit`, or `Bash`.
- Telemetry records only outcome, turns, elapsed time, and token counts. It never
  records the question or answer.
- The service is isolated from the mutating session lease. If the service or its
  read-only tools are unavailable, the operation reports `unavailable` and the
  capability is not advertised.

## Acceptance evidence

1. A fake agent can complete a question and receives only the four read tools.
2. A concurrent request returns `busy`; timeout and retry exhaustion return their
   classified outcomes and release the slot.
3. The operation record and telemetry contain no question/answer content.
4. Existing write endpoints remain unchanged and are not reachable through this
   surface.

## Residual risk

The provider adapter enforces its own tool-result truncation. O7's application
limits bound turns, deadline, question and answer sizes; a future adapter should
also expose an explicit per-question tool-result limit.
