# Revision Allocator Specification

Status: implemented for RC-2B Batch 1
Decision references: ADR-RC2-001, ADR-RC2-003, ADR-RC2-006, `REVISION-MANIFEST-SPEC.md`

## Seam and interface

`ProjectRevisionAllocator.execute(connection, transition, write_authority)` is the sole post-initialization revision-allocation interface. The caller must already hold a SQLite `BEGIN IMMEDIATE` transaction. The interface accepts the expected revision, stable command/commit/idempotency identities, request hash, transition/provenance/actor classifications, artifact reference/hash pairs, compatibility versions, accepted timestamp and pre-transition state hash. Its one callback receives the allocated revision and must atomically persist the concrete events/artifacts/projections, returning ordered event IDs and the resulting state hash.

The module is deep: callers do not calculate the next revision, construct a manifest, manage a bootstrap boundary, hash membership, or perform project-pointer CAS. `RevisionManifestRepository` is a separate read-only interface for `get`, `latest` and `list` and cannot create/update/delete manifests.

The allocator preserves the transition's supplied provenance ID and actor class. Bootstrap compatibility labels are used only for the separately inserted boundary manifest; they must never overwrite native command provenance.

## Transaction protocol

1. Resolve an existing manifest by project/idempotency key. Matching request hash returns it; mismatch fails.
2. Read and validate `projects.revision == expected_revision`.
3. Require the current revision manifest. For a pre-manifest project, establish exactly one bootstrap lineage start; a non-empty legacy revision 0 advances to boundary 1 without creating revision 0.
4. Calculate `next = current + 1` only inside the allocator.
5. Invoke the authority-write callback with `next`.
6. Reload ordered events by ID and hash their logical envelopes; sort artifact reference/hash pairs by reference then hash.
7. Build and insert the immutable manifest.
8. CAS `projects.revision` from current to next and update manifest writer metadata.
9. Return revision and manifest. The caller finalizes command/commit bookkeeping and commits the outer transaction.

Any exception rolls back authority rows, manifest and CAS together. A failed CAS after manifest insertion publishes neither. A caller rollback after a successful CAS also publishes neither. Finalized numbers are never reused; aborted transaction-local arithmetic is not a finalized allocation.

## Command integrations

- Native create inserts the project and `initialize_empty` revision-0 manifest in one transaction.
- Chapter finalize uses command ID `chapter.finalize:{commit_id}`, binds the stable commit ID and `chapter:{commit_id}` artifact hash, and creates one revision regardless of event count.
- Typed diff and scoped operator append use one deterministic `domain.command:*` identity and one manifest for all mutations.
- Prepare, validate, review, replay, recovery audit, snapshots, reads, export/index/outbox and migration workflow operations never call the allocator.

## Compatibility condition

Batch 1 does not invent `chapter.finalized` or `project.bootstrap_boundary` events before the Batch 2 closed catalog exists. A zero-event chapter/bootstrap manifest therefore uses `event_schema_version=legacy-unversioned`; chapter artifacts and projection state hashes remain linked. This is an explicit temporary coverage condition, not a claim that event coverage is complete.
