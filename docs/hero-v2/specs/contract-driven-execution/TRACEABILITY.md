# Contract-driven execution traceability

Status values: `Specified`, `Tested`, `Implemented`, `Verified`, `Blocked`.

## Requirement matrix

| Requirement | Decisions | Implementation | Automated evidence | Rendered/E2E | Status |
|---|---|---|---|---|---|
| CDE-001 | D003-D007, D013 | `8f92595`: domain model + SQLite v1-to-v2 migration | CDE-A01 plus exact round-trip and invalid-new-kind tests | N/A | Verified |
| CDE-002 | D001-D002 | `8f92595`: document catalog, preparation flow, phase inputs | CDE-A02 plus Research-from-seed test | Mission document UI pending | Implemented |
| CDE-003 | D001-D004 | `8f92595`: composite approval metadata and optimistic brief revision check | CDE-A03, CDE-A04 | Design Review pending | Implemented |
| CDE-004 | D005-D007, D011 | `0a4aa0b`: lossless operations, derived locators and relationship levels | CDE-A05 | N/A | Verified |
| CDE-005 | D003, D007, D014 | `0a4aa0b`: immutable snapshot-scoped slices and active alias | CDE-A06 plus Mission pipeline assertion | WorkPlan UI pending | Verified |
| CDE-006 | D005, D012, D014 | `0a4aa0b`: one alias included by all six contractual phases | CDE-A07 plus prompt obligations | N/A | Verified |
| CDE-007 | D005-D007, D011, D015 | `7fc61c1`: AST declaration/signature/docstring/relationship verifier; classic and interactive completion gate | CDE-A08, CDE-A09 plus required-unverifiable merge gate | Valid and invalid structural results rendered consistently for MCP, Chat, and Mission | Verified |
| CDE-008 | D008, D012, D016, D018, D020, D023 | `05bb7a6`: persisted execution history; `e869e62`: Mission actor integration; `b44771c`: execution-relative changed-file receipt; `a06e749`: terminal Mission validation evidence; `479839c`: clean signed-merge fallback | CDE-A10 plus Mission, Chat, MCP, completion, validation, blocker, committed-diff, baseline-isolation, Mission blocker evidence, and real Git fallback tests | Playwright rendered each actor's failed and completed/unowned states; live receipts preserve verifier and changed-file evidence | Verified |
| CDE-009 | D003, D009, D012, D016 | `05bb7a6` HARNESS authority; `hero-graph-lab@98025eb` typed MCP adapter | Real MCP initialize/list/call protocol test with simulated HARNESS worker | CDE-A11 verified against a live worker through real MCP STDIO initialize/list/get/begin/validate/complete calls | Verified |
| CDE-010 | D008, D010, D012, D017, D021 | `682e1d5` bounded HARNESS file/check tools; `hero-graph-lab@4c7e112` explicit Chat Implement mode; `hero-graph-lab@f86627d` schema-governed empty patch for target creation | CDE-A12 refusal before model; CDE-A13 contract toolchain; CAS/path/actor/check/file-creation tests | Playwright drove actual Chat Implement tools for invalid and valid implementations and rendered the terminal result | Verified |
| CDE-011 | D006, D011, D019, D022, D024 | `hero-graph-lab@03b37ff` authority-backed contract card and generated interface preview; `a06e749` verifier-backed relationship reconciliation; `hero-graph-lab@4f23582` source-aware graph cache | DOM contract assertions, relationship evidence tests, graph-cache refresh test; Graph Lab full suite | CDE-A15 verified with Playwright for MCP, Chat, and Mission; valid nodes remained navigable after a branch/source change without restarting Graph Lab | Verified |
| CDE-012 | D001, D008 | Existing amendment flow to extend | CDE-A14 | Amendment UI pending | Specified |
| CDE-013 | All | Shared contract authority exercised through Mission, real MCP STDIO, and explicit Chat Implement | HARNESS 187 tests; Graph Lab 40 tests; valid and deliberately invalid executions for all three actors | Playwright rendered both terminal states and navigated the materialized implementation; provider inference boundary documented below | Verified |

## Baseline evidence

- Design proposal: `hero-graph-lab@030a11e`,
  `docs/design/contract-driven-execution.md`.
- HARNESS baseline: `08fb081` (`feat: add interactive mission control plane`).
- HARNESS baseline validation on 2026-08-15: 157 `unittest` tests passed;
  all 44 modified/new Python files passed Ruff before the baseline commit.
- Graph Lab baseline: clean at `030a11e` after its contract design document.

## Increment log

| Date | Commit | Increment | Evidence | Result |
|---|---|---|---|---|
| 2026-08-15 | `4e58a33` | SDD package | Requirements and decisions reviewed from design baseline | Specified |
| 2026-08-15 | `8f92595` | Contract schema, brief boundary and composite approval | 162 `unittest` tests; changed Python files pass Ruff; `git diff --check` clean | Verified backend; rendered UI pending |
| 2026-08-15 | `0a4aa0b` | Lossless ChangeSet and immutable task contract slices | 168 `unittest` tests; changed Python files pass Ruff; `git diff --check` clean | Verified backend and Mission pipeline; rendered UI pending |
| 2026-08-15 | `7fc61c1` | Python AST verification and Mission completion enforcement | 174 `unittest` tests; changed Python files pass Ruff; `git diff --check` clean | Verified backend in classic and interactive coordinators; materialization UI pending |
| 2026-08-22 | `05bb7a6`, `hero-graph-lab@98025eb` | Contract execution authority and MCP tools | Fresh run: HARNESS 179 tests; Graph Lab 35 tests; MCP protocol calls contract read and begin against simulated worker | Live HARNESS worker and rendered ownership state pending |
| 2026-08-22 | `682e1d5`, `hero-graph-lab@4c7e112` | Bounded Chat patch/check API and explicit Implement mode | HARNESS 181 tests; Graph Lab 38 tests; changed files pass Ruff; both JS files pass `node --check` | CDE-A12/A13 automated; rendered mode pending |
| 2026-08-22 | `e869e62`, `hero-graph-lab@03b37ff` | Mission lease integration and derived contract UX | HARNESS 182 tests; Graph Lab 38 tests; changed files pass Ruff; diffs clean | Automated state verified; browser plugin failed before tab creation |
| 2026-08-22 | `b44771c` | Execution-relative changed-file receipts | 9 contract-execution tests and 3 Git adapter tests passed; repeated live MCP completion reports only `src/notification_gateway.py` | Receipt bug found by E2E and corrected |
| 2026-08-22 | Documentation commit following `b44771c` | Live MCP contract E2E and rendered CDE-A15 | HARNESS 184 tests; Graph Lab 38 tests; changed Python files pass Ruff; invalid signature rejected; corrected signature passed 19 structural checks; Playwright rendered divergent and materialized states; fresh graph navigation reached the method | MCP path verified; Mission and Chat matrix still pending |
| 2026-08-22 | `hero-graph-lab@f86627d` | Chat can create an absent contract target through its bounded patch tool | 17 focused gateway tests; invalid Chat implementation blocked at two signature fields; corrected implementation passed and completed | Chat valid/invalid path verified in the rendered UI |
| 2026-08-22 | `a06e749` | Mission preserves blocker verification and reconciles exact verifier-backed hard relations | 11 reconciliation tests and 5 interactive coordinator tests; invalid Mission retained two failed checks; valid Mission materialized all five operations | Mission reached the merge boundary with authoritative evidence |
| 2026-08-22 | `479839c` | Signed merge fallback aborts the failed merge before retry | 4 Git adapter tests including a real temporary repository; final valid Mission merged to `develop` | Mission valid path completed instead of leaving `MERGE_HEAD` blocked |
| 2026-08-22 | `hero-graph-lab@4f23582` | Cached graph follows created and changed Python sources | Graph Lab 40 tests and Ruff; live graph changed from 19 to 23 nodes after worker branch checkout without server restart | Playwright navigated the new module and exact method signature in the same server process |

## Live Chat Implement E2E evidence - 2026-08-22

- Isolated branches: `contract-chat-invalid-3` and `contract-chat-valid`.
- Approved snapshot: `0c07ad207003`, design revision 1, task `T-1`.
- Invalid execution: `de8cdbfca9344666b0363419aa4a105e`, actor `chat`.
  The actual Chat Implement toolchain retrieved the task, acquired the lease,
  read the target, created it through the bounded patch gateway, ran the
  configured check, and invoked the common verifier. The deliberately wrong
  `chat_id: int` annotation and missing return annotation produced exactly two
  failures. Completion was refused, Chat reported the blocker, and the lease
  was released.
- Valid execution: `78883775d3b74ef6a8bb15cedc608e00`, actor `chat`. The
  same tool sequence created the exact signature, passed configured checks and
  structural verification, and completed with only
  `src/notification_gateway.py` attributed to the execution.
- Playwright rendered the invalid contract as `divergent`, unowned, with two
  failed checks, and the valid contract as `materialized`, unowned, with the
  verifier passed. The final Chat response also reported the corresponding
  blocked or completed outcome.

Boundary: a deterministic model client selected the real Chat tools and supplied
the valid or invalid source so the test is repeatable. This verifies explicit
authorization, tool sequencing, bounded writes, checks, lifecycle, verifier,
and rendered state; it does not evaluate Gemini, OpenAI, or Anthropic instruction
following.

## Live Mission E2E evidence - 2026-08-22

- Isolated branches: `contract-mission-invalid-fixed` and
  `contract-mission-valid-final`.
- Approved snapshot: `0c07ad207003`, design revision 1, task `T-1`.
- Invalid execution: `3d578fb8f8da4792a0ff3d08f7587637`, actor `mission`.
  The real interactive coordinator ran SPEC, PLAN, IMPLEMENT, the configured
  check, and common verification. The deliberately wrong annotation and missing
  return annotation blocked the task with the exact two failures preserved in
  the execution receipt.
- Valid execution: `60a38c4b2c8c4a1eac9a7e05489b4895`, actor `mission`.
  The same pipeline passed verification, reconciled the module, class, method,
  and two containment relations as materialized, completed task and session,
  committed the source, and merged branch `contract-mission-valid-final` into
  `develop` at `57e20c8`.
- Playwright rendered the negative case as Mission `Blocked`, task `Failed`,
  contract `divergent`, and verifier `2 failed`; it rendered the positive case
  as Mission and task `Completed`, contract `materialized`, and verifier
  `passed`. Flow navigation reached the exact method and displayed its docstring
  and signature. The final cache test repeated that navigation after changing
  branches without restarting the Graph Lab server.

Boundary: a deterministic Mission agent produced repeatable SPEC, PLAN,
implementation, and report outputs while the real coordinator, gates, storage,
Git service, code-graph rebuild, reconciliation, lease, and verifier executed.
This verifies the Mission contract machinery, not the reasoning quality of an
external model provider.

## Live MCP E2E evidence - 2026-08-22

- Isolated project branch: `contract-e2e-receipt`.
- Approved snapshot: `8b6430e38a2a`, design revision 1, task `T-1`.
- Execution: `a681c0744e454da3bcd67b8bb26f6c5f`, actor `mcp`.
- The real MCP STDIO server initialized as `hero-graph-lab`, listed the
  contract tools, retrieved the immutable slice, and acquired the HARNESS
  worker lease.
- A deliberately wrong `chat_id: int` signature without `-> bool` failed the
  common verifier at both exact fields. Completion remained blocked and
  Playwright rendered `divergent`, owner `mcp`, and `verifier 2 failed`.
- The corrected `(self, chat_id: str, text: str) -> bool` implementation passed
  all 19 structural checks. Completion recorded final commit `39584c2`, zero
  failed checks, and only `src/notification_gateway.py` in `changed_files`.
- After restarting Graph Lab to force fresh extraction, Playwright rendered
  mission `Completed`, task `Completed`, contract `materialized`, snapshot and
  revision agreement, owner `unowned`, and `verifier passed`. Explorer and Flow
  navigation reached `NotificationGateway.send_notification` and displayed the
  exact implemented signature. The fresh browser tab had no console errors.

Boundary: the approved brief/design/snapshot fixture was produced through the
real HARNESS domain, storage, compiler, worker, verifier, and session schemas,
but without Research/Grill LLM inference. The configured MCP server was not
hot-loaded as a named tool into the already-open Codex session, so Codex drove
the same configured server through a real `mcp.ClientSession` STDIO connection.
This verifies the contract-execution path, not provider inference or Codex MCP
startup discovery.

## Verification policy

- Focused tests establish the changed contract only.
- The full repository suite is required before each implementation commit.
- Protocol initialization and actual tool calls are required for MCP claims.
- Playwright-rendered state is required for Chat and contract UX claims.
- A passing automated state model is not evidence that the rendered browser is
  correct.
