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
| CDE-007 | D005-D007, D011, D015 | `7fc61c1`: AST declaration/signature/docstring/relationship verifier; classic and interactive completion gate | CDE-A08, CDE-A09 plus required-unverifiable merge gate | Materialization UI pending | Verified |
| CDE-008 | D008, D012, D016, D018, D020 | `05bb7a6`: persisted execution history; `e869e62`: Mission actor integration; `b44771c`: execution-relative changed-file receipt | CDE-A10 plus Mission, Chat, MCP, completion, validation, blocker, committed-diff, and baseline-isolation tests | Playwright rendered active owner `mcp`, failed verification, and completed/unowned state; live MCP returned the corrected terminal receipt | Verified |
| CDE-009 | D003, D009, D012, D016 | `05bb7a6` HARNESS authority; `hero-graph-lab@98025eb` typed MCP adapter | Real MCP initialize/list/call protocol test with simulated HARNESS worker | CDE-A11 verified against a live worker through real MCP STDIO initialize/list/get/begin/validate/complete calls | Verified |
| CDE-010 | D008, D010, D012, D017 | `682e1d5` bounded HARNESS file/check tools; `hero-graph-lab@4c7e112` explicit Chat Implement mode | CDE-A12 refusal before model; CDE-A13 contract toolchain; CAS/path/actor/check tests | Rendered mode validation blocked by browser plugin bootstrap | Implemented |
| CDE-011 | D006, D011, D019 | `hero-graph-lab@03b37ff` authority-backed contract card and generated interface preview | DOM contract assertions; Graph Lab full suite | CDE-A15 verified with Playwright: `divergent`/owner `mcp`/2 failures, then `materialized`/unowned/passed; fresh graph extraction navigated to the implemented method | Verified |
| CDE-012 | D001, D008 | Existing amendment flow to extend | CDE-A14 | Amendment UI pending | Specified |
| CDE-013 | All | MCP path complete; Mission and Chat paths remain partial | Full suites plus the live MCP valid/invalid execution below | MCP path has live-worker and rendered evidence; equivalent valid/invalid Mission and Chat E2Es remain pending | Blocked |

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
