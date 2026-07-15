# RC-2B Batch 1 Implementation Report

Date: 2026-07-15
Baseline: `cefed3baffacea6fce715b856cc89bdfeaabc521`
Scope: RC-2B Batch 1 only

## Closeout outcome

The candidate implements native revision 0, one unified CAS allocator, immutable project revision manifests, a canonical SHA-256 predecessor chain, one honest legacy bootstrap boundary, doctor diagnostics, architecture gates, contract fail-closure and regression coverage. The cleaned local pre-commit matrix passed. Batch 2 was not started, no historical state API was opened, and no push or PR is part of this closeout.

Closeout review found and fixed one Batch 1 defect before the final test run: native post-initialization manifests discarded the supplied command provenance/actor and incorrectly labeled them as bootstrap compatibility. The allocator now preserves the caller-supplied native provenance and actor, tests assert it, and doctor additionally detects manifests with no corresponding committed command or finalized chapter transition.

## Implemented

- Migration 8 additively introduces project history-boundary metadata, writer compatibility metadata and `project_revisions` with unique revision/manifest/hash/command/idempotency/commit identities.
- SQLite triggers reject ordinary manifest UPDATE and DELETE; project deletion is restricted while manifests exist.
- `ProjectRevisionAllocator` owns precondition checking, legacy boundary establishment, next-revision arithmetic, authority callback execution, event/artifact membership hashing, immutable insert and project-pointer CAS inside one caller-owned transaction.
- Native project creation atomically creates an empty revision-0 manifest. Legacy schema migration creates no synthetic manifest rows; the first governed write or cutover establishes one boundary only.
- Chapter finalize, typed diff and scoped operator append route through the same allocator. Revision-neutral operations remain outside it.
- Doctor verifies latest pointer, manifest/previous hashes, membership hash, event envelopes/ranges/revision links, chapter artifact hashes, compatibility values and committed transition linkage without repairing authority.
- `at_revision` returns `409 HISTORY_NOT_IMPLEMENTED`; it never returns latest state under an older requested number.

## Temporary compatibility

- Existing legacy events may retain `schema_version=NULL` and `applied_revision=NULL` before the boundary.
- A chapter/bootstrap transition may have zero events under `event_schema_version=legacy-unversioned` until Batch 2 closes the catalog.
- Bootstrap represents current-state provenance with a state hash and existing finalized chapter artifact references. It does not reconstruct pre-boundary state.
- Migration interruption preserves a verified schema-7 backup and fails closed on retry while that backup path exists; operator inspection is required before another attempt.

## Deferred to Batch 2 or later

- Closed typed event catalog, mandatory `chapter.finalized`, complete event coverage and append-only event authority.
- Historical state tables/intervals, historical reducers/materialization, replay redesign and historical snapshots.
- Public historical query service, TypeScript historical client and Studio/CLI/TUI time travel.
- Any later-batch feature flag or user-facing history availability surface.

## Explicit non-claims and known limits

- This is still **not complete Event Sourcing**.
- Event coverage remains a **Batch 2** responsibility.
- `at_revision` still does **not** expose real history; it fails closed.
- A manifest proves revision existence and transition membership/integrity; **a manifest is not historical state**.
- History before a bootstrap boundary is unavailable and is not synthesized.
- Linux and macOS execution for the unpushed candidate is NOT VERIFIED.
- One initial CLI run exceeded the command ceiling, and one initial Chromium timeout-recovery case failed; unchanged final runs passed and both attempts are preserved in the test report.

## Data-authority separation

- Manifest: revision existence, transition summary, predecessor/hash chain, command/commit/event/artifact indexes, provenance and compatibility versions.
- Event: concrete domain-change expression, explicitly incomplete until Batch 2.
- Artifact: chapter body, review and other large immutable payloads.

The manifest schema contains no complete chapter/review body, complete event payload, complete story state, projection or independently substitutable state artifact.

## Pre-commit questions

| # | Question | Result | Evidence |
|---:|---|:---:|---|
| 1 | Changes belong only to Batch 1 | YES | inventory and scope search |
| 2 | No Batch 2 implementation | YES | no catalog/history/replay/client/UI implementation |
| 3 | No pseudo historical API | YES | `HISTORY_NOT_IMPLEMENTED` contract/API test |
| 4 | No fabricated old history | YES | additive migration and boundary tests |
| 5 | All revision increments use allocator | YES | G12/G13/G19 plus source trace |
| 6 | Every new revision has a manifest | YES | one transaction, CAS rollback tests and doctor |
| 7 | Manifest immutable | YES | triggers, repository boundary and tests |
| 8 | Hash chain verifiable | YES | canonical/predecessor/event/artifact tamper tests |
| 9 | Bootstrap boundary honest | YES | schema-7, positive-R and nonempty-R0 tests |
| 10 | Doctor detects inconsistency | YES | pointer, transition, hash, event and artifact diagnostics |
| 11 | All required tests rerun and finally pass | YES | `RC-2B1-TEST-REPORT.md` |
| 12 | No temporary files in candidate | YES | generated outputs re-cleaned before staging |
| 13 | Documentation matches code | YES | closeout review and explicit non-claims |
| 14 | Worktree can form one clear commit | YES | only classified RC-2/Batch 1 paths selected; RC-1 files excluded |

Pre-commit verdict: `RC-2B BATCH 1 READY TO COMMIT`.
