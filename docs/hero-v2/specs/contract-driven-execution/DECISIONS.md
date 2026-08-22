# Contract-driven execution decision log

This log is append-only. Status is `Accepted` unless stated otherwise.

## CDE-D001 - Approve after Grill

Date: 2026-08-15

Research and Grill operate on a mutable design draft. The human-approved
contract boundary follows Grill, when the reviewed brief and map can be checked
together. Approving before Research would freeze an untested hypothesis.

## CDE-D002 - Preserve a separate brief seed

Date: 2026-08-15

A user-supplied detailed brief is stored as `brief-seed.md`; `brief.md` remains
the reviewed output of Grill. This keeps provenance and approval semantics clear
without discarding useful initial detail.

## CDE-D003 - HARNESS owns the contract

Date: 2026-08-15

HARNESS owns design persistence, approval, snapshot, ChangeSet, task slices,
execution lease, and reconciliation. Graph Lab is an editor/visualizer and MCP
is a transport adapter. Multiple contract stores were rejected because their
revisions and completion state would drift.

## CDE-D004 - Use a forward SQLite migration

Date: 2026-08-15

The design database contains authorial data and operation history. Schema v2
will use explicit `ALTER TABLE` migration with safe defaults and a transaction.
Destructive recreation or silent rejection of a v1 database is unacceptable.

## CDE-D005 - Python first

Date: 2026-08-15

The first structural verifier supports Python, matching the current analyzer and
Graph Lab extractor. Contract fields remain language-neutral enough to add
adapters later, but no generic verifier framework is introduced prematurely.

## CDE-D006 - Docstring presence, not exact text

Date: 2026-08-15

Docstrings are mandatory when declared for a class, function, or method. Exact
wording is reviewable rather than byte-matched, because harmless clarification
should not create structural divergence.

## CDE-D007 - Signature annotations are contractual

Date: 2026-08-15

When a signature is supplied, parameter order, names, default presence,
annotations, and return annotation are contractual. This provides meaningful
interface assurance; checking only arity would allow incompatible APIs.

## CDE-D008 - One execution lease per mission

Date: 2026-08-15

Mission, Chat, and MCP/Codex may take turns but not concurrently mutate one
mission workspace. Task-level parallel worktrees are deferred until demand and
merge semantics justify them.

## CDE-D009 - Codex keeps native editing tools

Date: 2026-08-15

MCP supplies pinned contract context and lifecycle operations. Codex continues
to use its native contained workspace tools for edits and tests. A generic MCP
shell or duplicate filesystem protocol is rejected. A later bounded patch tool
may be added only if portability requires it.

## CDE-D010 - Explicit Chat Implement authorization

Date: 2026-08-15

Chat implementation requires an explicit UI mode plus an approved mission and
available lease. Natural-language intent detection is insufficient authorization
for source mutation.

## CDE-D011 - Hard and advisory relations remain distinct

Date: 2026-08-15

Containment, resolved imports, and inheritance may become hard gates. Relations
without deterministic analyzer evidence remain advisory and must not be reported
as materialized merely because an agent claims compliance.

## CDE-D012 - Share services, not transports

Date: 2026-08-15

Mission calls the contract service directly, Graph Lab Chat uses an internal
adapter, and external agents use MCP. Mission does not call its own MCP server;
that would add transport failure modes and a Graph Lab/HARNESS lifecycle cycle.

## CDE-D013 - Preserve unknown legacy kinds explicitly

Date: 2026-08-15

Schema-v1 CODE rows do not contain enough evidence to distinguish class,
function, and method, while PACKAGE rows conflate packages and modules.
Migration records `unknown` instead of guessing from labels or capitalization;
only SYSTEM is unambiguous. Contract-aware clients must supply an exact kind for
new nodes. Legacy `unknown` CREATE nodes remain incomplete and later compilation
will report them as issues.

## CDE-D014 - Version task contracts by approved snapshot

Date: 2026-08-15

Each task contract is stored at
`task-contracts/<snapshot-id>/<task-id>.json`. Recompiling the same task and
snapshot must produce identical bytes; a different payload at that path is a
conflict. The mutable `task-contract.json` file is only an execution-time alias
to the selected immutable slice, allowing every phase to use one stable include
without weakening snapshot immutability.

## CDE-D015 - Verify Python statically before task completion

Date: 2026-08-15

HARNESS parses required Python targets with the standard-library AST and never
imports or executes project code for structural verification. Both classic and
interactive Mission routes call the same verifier before marking a task
complete. Failures are written with node-and-field evidence to
`contract-verification.json` and block completion; advisory relationships do
not block.

## CDE-D016 - Keep MCP execution state in HARNESS

Date: 2026-08-22

HARNESS owns the persisted execution history, active-lease conflict check,
contract validation, task completion, blocker, and amendment transitions.
Graph Lab contributes only typed MCP tools and forwards them to the active
HARNESS worker, always pinning external calls to actor `mcp`. This preserves one
authority and does not expose a generic shell or filesystem mutation tool.
