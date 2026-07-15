# ADR-RC2-001: Project Revision Semantics

- Status: Accepted
- Decision: **APPROVED**
- Date: 2026-07-15

## Context

`projects.revision` currently records only latest, while commits, imports, reviews, replay and recovery use several unrelated ledgers. A single project story revision must identify an atomic authoritative story-state transition without confusing workflow activity, projection repair or migration audit with story history.

## Decision

1. A story revision is scoped to exactly one project, is monotonic, immutable and never reused.
2. A native project is created at revision 0, representing an empty initialized story state. Creation of the project container is not revision 1.
3. One successful atomic story-state command creates exactly one new revision and one finalized manifest, regardless of event count. One finalized chapter therefore increments exactly once.
4. Idempotent retry returns the prior result and creates no revision, event or manifest.
5. Replay, snapshot, projection/index/outbox repair, export, review artifacts, human review decisions and migration workflow audit are revision-neutral.
6. A finalized authoritative replacement of a chapter body or its story state is a new story-state command and increments once. Draft edits, proposed revisions and validation do not.
7. Logical rollback, compensation, tombstone, restore and alias merge are forward transitions and create new revisions; they never rewind a project pointer.
8. No gaps are allowed after the first finalized manifest in a Runtime-managed lineage: `previous_revision = revision - 1`. A legacy bootstrap may begin at `R > 0`; missing values before R are an **availability boundary**, not revision gaps or implied manifests.
9. Verified import may create several revisions only when source order and atomic command boundaries are evidenced. Source numbering is retained as provenance, not used to introduce gaps into the Runtime ledger.

## Command classification

Story-state commands include finalized chapter creation/replacement; entity, relationship, fact, resource, timeline, thread, foreshadow, world-rule and alias transitions; story-significant project metadata; bootstrap/verified-import authority transitions; tombstone, restore and compensation.

Not story-state commands include prepare/validate/review, human decisions, status polling, job state, idempotency bookkeeping, outbox/index/search/cache work, snapshot, replay/verify/repair, backup, schema migration, authorization changes and operational phase changes.

Project metadata enters story revision only when it changes the authored world or reader-visible canonical work (for example canonical title/series identity or declared story status). Runtime health, filesystem location, UI preferences, access policy and workflow phase do not. The closed command catalog must classify each metadata field before it can mutate authority.

## Migration and authority mode

- Current-state bootstrap establishes the imported state at one boundary revision R. If a trustworthy existing non-zero revision exists, preserve it as R. If non-empty state claims revision 0 or has no trustworthy number, allocate R=1. Pre-R state is unavailable.
- The `authority_mode` flip is an operational cutover record. It is not a second story revision. For current-state-only migration, the same transaction finalizes the bootstrap manifest/event and cutover audit; for native or already-verified state, a pure mode change stays revision-neutral.
- Every mode transition is recorded in immutable migration provenance with actor, source/target mode, reason, timestamp, checksums and the related manifest ID when a bootstrap/verified transition exists.

## Atomicity and gaps

The manifest, ordered events, immutable artifact references, history-table updates, current projection updates and `projects.revision` compare-and-swap commit in one SQLite transaction. A failed command leaves none finalized. Reserved-but-aborted numbers are not visible and are reused only because they were never finalized; finalized revision numbers are never reused.

## Consequences

- `chapter_commits`, migration audit and `idempotency_ledger` remain evidence/operational records, not substitutes for the revision ledger.
- Batch 1 can freeze allocation and manifests without knowing Batch 2 domain payload schemas; it may store version identifiers and event hashes but must not invent payloads.
- Native projects have a queryable revision 0. Bootstrap legacy projects do not gain a fabricated empty revision 0.
