# RC-2B1 Preimplementation Audit

Date: 2026-07-15
Scope: RC-2B Batch 1 only
Baseline: `master@cefed3baffacea6fce715b856cc89bdfeaabc521` plus the untracked, approved RC-2A/RC-2A.5 documents
Decision references: ADR-RC2-001 through ADR-RC2-007, `REVISION-MANIFEST-SPEC.md`, `RC-2-DATA-OWNERSHIP-MATRIX.md`

## Executive finding

The current Runtime has no authoritative revision ledger. `projects.revision` is a latest pointer advanced independently by chapter finalize, operator/typed-diff append, and legacy import. `chapter_commits`, `story_events`, artifacts, migration ledgers, idempotency records, replay jobs and outbox rows are useful evidence or workflow records, but none proves that a project revision exists. Batch 1 therefore must introduce one deep `ProjectRevisionAllocator` module whose interface owns validation, lineage bootstrap, manifest finalization and project-pointer CAS inside the caller's existing `BEGIN IMMEDIATE` transaction.

The manifest will prove revision identity, membership, integrity and provenance only. It will not contain chapter bodies, complete event payloads, projections, snapshots or diffs. Existing story events continue to express the concrete domain changes, with their closed catalog and complete envelope explicitly deferred to Batch 2. Existing chapter artifacts continue to own large chapter bytes and are referenced only by stable identifiers and hashes.

## Audited paths

### Project initialization

`ChapterCommitService.create_project` begins `BEGIN IMMEDIATE`, checks the shared idempotency ledger, inserts a Runtime-authority project at revision 0, records the result and commits. It currently creates no revision-0 proof. `StoryRepository.initialize_fixture` is a legacy/test bootstrap path: it accepts a supplied current revision, directly inserts current projections and unversioned events, and records fixture idempotency. It must not be mistaken for native empty initialization.

### Chapter lifecycle and commit transaction

Prepare and validate are separate transactions and do not advance project revision. Validate persists the chapter artifact before finalization. Finalize begins `BEGIN IMMEDIATE`, rechecks commit state, artifact hash, Runtime authority and expected revision, computes `expected_revision + 1`, appends zero or more events, applies projections, writes the chapter summary, directly CAS-updates `projects.revision`, checkpoints projections, finalizes the commit, adds outbox work and updates the idempotency result in the same transaction. Atomic rollback is already structurally available, but there is no manifest between authority writes and CAS.

### Typed diff and operator command

`apply_typed_diff` validates a small typed allow-list and then adapts to `append_operator_events`. The latter has its own transaction, idempotency check, `expected_revision + 1`, event append/reducer loop, direct project CAS, checkpoint/outbox writes and commit. It is a second allocator. Arbitrary operator append remains an administrative escape hatch; Batch 1 must force it through the same allocator/manifest transaction, while Batch 2 remains responsible for closing the catalog and may not be claimed complete here.

### Migration import and cutover

`LegacyMigrationService._import_cir` imports in batches of 100. `_import_item` currently increments revision once for every imported legacy event and once for every imported chapter. The batch then overwrites `projects.revision`. This invents atomic history from row count and is a third allocator. Imported legacy events may have `applied_revision` values created by this arithmetic. Cutover changes only `authority_mode` and audit state. Batch 1 must stop per-row allocation, keep old/unproven events outside authentic revision membership, and establish one explicit current-state bootstrap boundary before Runtime authority writes.

### Review and revision artifacts

Review artifact validation, human decisions and revision-result validation write `review_*`, `human_review_decisions` and `revision_results` operational/proposal records. They do not currently update `projects.revision` and must remain revision-neutral unless a revised body is later finalized through the chapter authority command.

### Replay, snapshot, outbox and recovery

Replay jobs do not change `projects.revision`, but non-verify replay currently clears and rebuilds current projections; Batch 1 must test revision neutrality and must not claim the approved isolated replay semantics are implemented. Snapshot/export/index/outbox operations are derived work and do not update the project pointer. Commit recovery may delete events belonging to an unfinalized commit, rebuild finalized projections and retry the original finalize. It can currently rely on the same expected revision after rollback; once manifests exist, recovery must never delete a finalized manifest or reuse a finalized revision.

### Idempotency and response loss

Project create and operator append use `idempotency_ledger`. Chapter prepare owns the lifecycle key and finalize rewrites its stored result. A response lost after `COMMIT` is retried by detecting an existing finalized commit or idempotency row. There is no stable manifest identity/hash in those results today. Conflicting reuse is checked by request hash for project create, prepare and operator append. Typed diff performs validation before delegating except when the key already exists, in which case it delegates for request-hash comparison.

### Transactions, locks and Windows SQLite

Authority writes use SQLite `BEGIN IMMEDIATE`, WAL, `foreign_keys=ON`, configurable `busy_timeout`, `synchronous=NORMAL`, and project-pointer compare-and-swap. Connections use `isolation_level=None` and `check_same_thread=False`. On Windows, a competing writer receives retryable `DATABASE_LOCKED`; WAL files and open handles can delay replacement/checkpoint operations, so tests must use local-disk temporary databases, close connections deterministically, and cover writer contention. Global event `sequence` is physical; project-local ordered IDs/ordinals, not gap-free global sequences, must define manifest membership.

## Required answers

1. **Which paths increase project revision now?** Chapter finalize, operator append (and therefore typed diff), and legacy import event/chapter rows. Test fixtures and replay helpers can also seed/overwrite revisions directly but are not production authority commands.
2. **Is any path updating revision before other records?** No production path commits the pointer in a separate earlier transaction. Chapter/operator update it after event/projection writes but before final commit/finalize bookkeeping. Import repeatedly computes row-derived revisions and writes the pointer at each batch end. None writes a manifest.
3. **Are there multiple allocators?** Yes: chapter finalize, operator/typed-diff append, and migration import.
4. **Can retry add revision twice?** Normal same-key chapter/operator retries are guarded, but there is no manifest-level command uniqueness. Recovery and migration batching depend on separate ledgers/state and can diverge from a future ledger unless unified. Response-loss identity is not yet anchored to an immutable manifest.
5. **Do chapter commit and typed diff share an allocator?** No. They duplicate revision arithmetic and CAS.
6. **How does migration set revision?** It begins at the target's current value and increments once per imported event and chapter, then writes the batch result to `projects.revision`. This is prohibited fabrication for current-state-only input.
7. **Does replay incorrectly change revision?** It does not change `projects.revision`. Non-verify replay can change latest projections and checkpoints and is not yet the approved isolated/latest-only repair model; that semantic repair remains outside Batch 1.
8. **Can recovery reuse a revision?** Today an aborted SQL transaction consumes no visible number, so retry reuses the arithmetic next value. Recovery deletes only unfinalized-commit events and retries. Without manifests it cannot distinguish finalized ledger membership independently; Batch 1 must make finalized manifest existence decisive and immutable.
9. **Which operations must remain revision-neutral?** Prepare, validate, review artifact validation, human review decisions, revision-result validation/proposal, replay verify and projection repair, snapshot, export, index, outbox, doctor, recovery audit/abort, migration scan/dry-run/snapshot/verify workflow, UI/read/query operations, failed commands and duplicate retries.
10. **Which old projects cannot receive historical manifests?** Any fixture/import/project with populated current projections but no complete externally evidenced command order; projects with null `applied_revision` events; projects with arbitrary/unversioned events; projects whose revision was derived from imported row count; and current-only projects lacking a genuine empty revision 0. They require one explicit bootstrap boundary and must not receive fabricated intermediate manifests.

## Implementation constraints frozen by this audit

- The allocator seam is inside an already-open `BEGIN IMMEDIATE` transaction and is the only production code allowed to calculate or CAS the next revision.
- A native project transaction creates the project row and revision-0 manifest together.
- A current-only lineage receives one bootstrap boundary at its honest current boundary before its first new Runtime command; no `0..R-1` rows are synthesized.
- Manifest canonical data includes stable logical fields and the accepted command timestamp; it excludes `manifest_id`, `manifest_hash` and physical database-generated identifiers.
- Event arrays preserve ordinal order. Artifact reference pairs use deterministic type/reference ordering. Null and empty remain distinct canonical JSON values.
- SQLite triggers and the repository interface prohibit update/delete of finalized manifests. Project retention/deletion policy must be explicit; ordinary cascading deletion is not accepted as a manifest mutation path.
- Migration 8 is additive. Once schema 8 contains manifest authority, schema-version negotiation blocks older writers; downgrade after new manifest writes is a stop-and-restore/compatible-reader operation, not a destructive SQL rollback.
- Batch 1 may record `legacy-unversioned` compatibility identifiers and zero-event chapter/bootstrap compatibility where no closed-catalog event exists. This is explicitly incomplete coverage, not a Batch 2 substitute.
