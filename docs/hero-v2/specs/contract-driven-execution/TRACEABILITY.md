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
| CDE-008 | D008, D012, D016, D018 | `05bb7a6`: persisted execution history; `e869e62`: Mission actor integration | CDE-A10 plus Mission, Chat, MCP, completion, validation, and blocker tests | `hero-graph-lab@03b37ff` renders owner; browser validation blocked by plugin bootstrap | Implemented |
| CDE-009 | D003, D009, D012, D016 | `05bb7a6` HARNESS authority; `hero-graph-lab@98025eb` typed MCP adapter | Real MCP initialize/list/call protocol test with simulated HARNESS worker | Live-worker CDE-A11 pending | Tested |
| CDE-010 | D008, D010, D012, D017 | `682e1d5` bounded HARNESS file/check tools; `hero-graph-lab@4c7e112` explicit Chat Implement mode | CDE-A12 refusal before model; CDE-A13 contract toolchain; CAS/path/actor/check tests | Rendered mode validation blocked by browser plugin bootstrap | Implemented |
| CDE-011 | D006, D011, D019 | `hero-graph-lab@03b37ff` authority-backed contract card and generated interface preview | DOM contract assertions; Graph Lab full suite | CDE-A15 blocked: in-app browser bootstrap rejected its own `node:process` import before opening a tab | Implemented |
| CDE-012 | D001, D008 | Existing amendment flow to extend | CDE-A14 | Amendment UI pending | Specified |
| CDE-013 | All | Partial across Mission, MCP protocol, and Chat tests | HARNESS 182 tests; Graph Lab 38 tests | Real live-worker MCP, rendered browser, and valid/invalid three-path matrix remain pending | Blocked |

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

## Verification policy

- Focused tests establish the changed contract only.
- The full repository suite is required before each implementation commit.
- Protocol initialization and actual tool calls are required for MCP claims.
- Playwright-rendered state is required for Chat and contract UX claims.
- A passing automated state model is not evidence that the rendered browser is
  correct.
