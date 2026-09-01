# Contract-driven execution specification

Status: Approved for incremental implementation
Date: 2026-08-15
HARNESS baseline: `08fb081`
Design baseline: `hero-graph-lab@030a11e`
Design source: `docs/design/contract-driven-execution.md` in `hero-graph-lab`

## Problem

The shared design map already produces an approved snapshot, a ChangeSet, and a
WorkPlan, but its current node contract loses the exact code kind and carries no
target path, signature, docstring, or behavioral acceptance identifiers. Task
SPEC, PLAN, IMPLEMENT, and REVIEW consume derived prose rather than one exact
task-scoped contract. Graph Lab Chat, external MCP clients, and Mission therefore
cannot yet prove that they implement the same approved design.

## Goals

1. Preserve exact structural and behavioral obligations from design draft to
   observed implementation.
2. Bind the approved brief and design revision into one immutable contract
   snapshot.
3. Compile one deterministic task contract slice and provide it unchanged to
   every reasoning and execution phase.
4. Enforce the same completion rules for Mission, Graph Lab Chat, and Codex via
   MCP.
5. Keep Graph Lab as editor/visualizer, HARNESS as contract authority, and MCP as
   an adapter rather than another store.
6. Deliver the work incrementally with requirement, decision, test, browser, and
   commit traceability.

## Non-goals

- Generate complete business logic while proposing graph nodes.
- Write source or stub files before execution approval.
- Support multiple concurrent executors for one mission in the first release.
- Expose an unrestricted shell or filesystem through MCP.
- Replace Research, Grill, SPEC, PLAN, or REVIEW with the graph.
- Treat advisory semantic relationships as deterministically materialized.
- Support non-Python structural verification in the first release.

## Terminology and authority

- A **brief seed** is human input to Research and Grill. It is not approved
  merely because it is detailed or named `brief.md` by its author.
- An **approved brief** is the reviewed mission-level behavioral authority.
- A **design draft** remains mutable through Research and Grill.
- A **contract snapshot** immutably binds approved brief revision, design
  revision, observed revision, and Git baseline.
- A **task contract slice** is the exact subset of snapshot nodes, relations,
  ChangeSet operations, and brief requirements covered by one WorkPlan task.
- Source plus fresh analysis is authoritative for observed state; the approved
  contract is authoritative for desired state; verifier evidence is authoritative
  for completion.

## Requirements

### CDE-001 - Versioned exact node contract

HARNESS shall extend `DesignNode` with:

- exact `kind`: `system`, `package`, `module`, `class`, `function`, or `method`;
- `target_path` for the intended repository-relative source location;
- `qualified_name` where a code symbol is expected;
- `signature` for functions and methods;
- `docstring` for classes, functions, and methods;
- `satisfies`, a bounded list of approved brief requirement identifiers;
- `acceptance`, a bounded list of behavioral acceptance statements.

The SQLite design store shall use a forward schema migration that preserves
existing authorial nodes and operations. Existing rows shall receive explicit
empty/default contract values, including a visible `unknown` kind when the v1
level cannot determine an exact code kind; the migration shall never recreate or
discard the database. New contract-aware clients shall not create `unknown`
nodes.

### CDE-002 - Brief seed is distinct from approved brief

The interactive mission document catalog shall preserve a supplied mature brief
as `brief-seed.md` with HUMAN provenance. Research and Grill shall consume it as
input. Grill remains responsible for producing the reviewed `brief.md`.

The existing `idea.md` path remains supported. No automatic fast-path approval is
introduced in the first release.

### CDE-003 - Immutable composite approval

Design approval shall record in the approved snapshot:

- `snapshot_id`;
- `design_revision`;
- `observed_revision`;
- approved brief logical id and revision;
- repository commit at approval;
- project identity;
- complete node and relation contracts;
- creation timestamp and provenance already held by the design store.

Approval shall fail when the requested design revision or reviewed brief
revision is stale. Existing snapshots remain immutable.

### CDE-004 - Lossless ChangeSet compilation

Every node operation in `changeset.json` shall preserve the exact contract fields
required to implement and verify its target. A CREATE operation for a required
repository code node shall be rejected as a compile issue when neither a valid
target path nor a deterministically derivable locator is available.

Relationships shall carry an explicit verification level: `hard`, `resolved`,
or `advisory`. The first release treats `contains`, resolved `imports`, and
`inherits` as hard-capable; custom semantic relationships remain advisory.

### CDE-005 - Deterministic task contract slices

After Structure passes exact operation coverage validation, HARNESS shall create
one immutable JSON task slice per task. Each slice shall contain:

- snapshot and design revision;
- brief revision and referenced requirements;
- task id, `covers`, dependencies, and target node ids;
- covered ChangeSet operations;
- target node contracts and required relationships;
- base commit and project identity.

Generation shall fail when a task references an unknown operation or node. Two
generations from identical inputs shall be byte-for-byte equivalent except for
an optional file-ending newline.

### CDE-006 - One phase context contract

SPEC, PLAN, IMPLEMENT, IMPLEMENT_BURSTS, REVIEW, and REIMPLEMENT shall receive
the same task slice through a `TASK_CONTRACT` include. Agents may elaborate it in
prose but shall be instructed not to rename, relocate, weaken, or remove an
obligation without requesting an amendment.

### CDE-007 - Python structural verifier

For required Python code nodes, the verifier shall inspect repository source via
AST and report at least:

- target path exists;
- symbol and exact kind exist;
- qualified parent/name matches;
- parameter names, order, default presence, and annotations match the declared
  signature;
- return annotation matches when declared;
- required docstring is present, without requiring exact wording;
- required base classes match when declared later by the schema;
- hard-verifiable containment and inheritance relations match.

A required structural obligation with insufficient evidence is blocking; it
must not silently pass as `UNVERIFIABLE`.

### CDE-008 - Shared execution lifecycle

HARNESS shall own a single active execution lease per mission. The lease records
execution id, actor (`mission`, `chat`, or `mcp`), task, snapshot, branch, base
commit, timestamps, changed files, final commit, and verifier result.

Inspection remains available while a lease is active. A second implementation
attempt is rejected until the first is completed, blocked, or explicitly handed
off.

### CDE-009 - MCP contract control plane

Graph Lab MCP shall expose bounded tools backed by the HARNESS worker contract
API for listing tasks, retrieving a task slice, beginning execution, validating,
completing, reporting a blocker, and proposing an amendment.

The adapter shall operate on the active Graph Lab project and active/resumable
mission. It shall not maintain snapshots or completion state. Codex may edit with
its native workspace tools; MCP owns contract retrieval and lifecycle evidence.

### CDE-010 - Explicit Chat Implement mode

Graph Lab Chat shall gain an explicit `Implement` mode. It shall never infer code
write authorization from natural-language keywords. The mode is available only
for a matching active/resumable mission with approved design and execution and
no competing lease.

Chat file changes shall be project-contained and patch-based. Test execution
shall use configured/bounded checks rather than an unrestricted model-controlled
shell.

### CDE-011 - Contract UX and state transition

Graph Lab shall render exact contract metadata and a generated interface preview
without writing source files. It shall show snapshot revision, task ownership,
execution actor, and verification state.

A proposal becomes materialized only after HARNESS rebuilds the observed graph
and the common verifier passes. Divergent and advisory states remain visually
distinct.

### CDE-012 - Amendments are revisioned

Any executor may report a contract defect. Execution shall pause at a safe
boundary, preserve evidence against the old snapshot, return to Amendment Review,
and require a new brief/design approval, ChangeSet, and WorkPlan validation.

No agent may silently mutate the approved snapshot or use later prose to override
it.

### CDE-013 - Three-path acceptance evidence

Completion requires equivalent end-to-end evidence for:

1. Mission implementing a contract task;
2. Codex retrieving and closing the task through real MCP;
3. Graph Lab Chat implementing through explicit Implement mode.

Each path shall be tested with one valid and one deliberately invalid structural
implementation. Rendered Playwright evidence is required for browser state; unit
or source assertions alone are insufficient.

## Acceptance scenarios

| ID | Scenario | Expected result |
|---|---|---|
| CDE-A01 | Open a schema-v1 design DB | It migrates forward with all authorial rows and history preserved |
| CDE-A02 | Save a detailed brief seed | It remains distinct from the Grill-produced approved brief |
| CDE-A03 | Approve a design with a stale brief or design revision | Approval returns a conflict and creates no snapshot |
| CDE-A04 | Approve a valid brief/design pair | Snapshot pins brief, design, graph, project, and commit baselines |
| CDE-A05 | Compile exact class/function contracts | ChangeSet preserves kind, path, signature, docstring, requirements, and acceptance |
| CDE-A06 | Structure a covered ChangeSet | Stable task contract slices are generated for every task |
| CDE-A07 | Run each task phase | The same slice content is present in every phase request |
| CDE-A08 | Verify correct Python declarations | Required nodes become materialized |
| CDE-A09 | Verify a missing/wrong signature or docstring | Completion is blocked with field-level evidence |
| CDE-A10 | Start a second executor | The lease conflict is explicit and no mutation is authorized |
| CDE-A11 | Use Codex through a real MCP client | It reads the pinned slice and records lifecycle transitions |
| CDE-A12 | Enter Chat Implement without approval | The mode is refused without changing source |
| CDE-A13 | Implement through Chat | Bounded patches and checks lead to the same verifier result |
| CDE-A14 | Request an amendment during execution | Old evidence remains and a new revision is required |
| CDE-A15 | Inspect the rendered UI | Contract preview, owner, revision, and materialization agree with HARNESS |

## Delivery order

1. Schema and artifact boundaries.
2. ChangeSet and task slice compilation.
3. Mission injection and structural enforcement.
4. MCP control plane.
5. Chat Implement mode.
6. Rendered UX and three-path E2E.

Every increment starts with failing contract tests, ends with the full relevant
suite, updates `TRACEABILITY.md`, and is committed independently.
