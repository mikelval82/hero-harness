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
| CDE-007 | D005-D007, D011 | Pending | CDE-A08, CDE-A09 | Materialization UI pending | Specified |
| CDE-008 | D008, D012 | Pending | CDE-A10 | Ownership UI pending | Specified |
| CDE-009 | D003, D009, D012 | Pending | Protocol tests | CDE-A11 | Specified |
| CDE-010 | D008, D010, D012 | Pending | Authorization/tool tests | CDE-A12, CDE-A13 | Specified |
| CDE-011 | D006, D011 | Pending | Preview/state tests | CDE-A15 | Specified |
| CDE-012 | D001, D008 | Existing amendment flow to extend | CDE-A14 | Amendment UI pending | Specified |
| CDE-013 | All | Pending | Full suites | CDE-A11-CDE-A15 | Specified |

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

## Verification policy

- Focused tests establish the changed contract only.
- The full repository suite is required before each implementation commit.
- Protocol initialization and actual tool calls are required for MCP claims.
- Playwright-rendered state is required for Chat and contract UX claims.
- A passing automated state model is not evidence that the rendered browser is
  correct.
