# Bootstrap Boundary Implementation

## Native versus legacy

A native project is created at revision 0 with one `initialize_empty` manifest, no previous revision/hash, no events and no fabricated entities/chapters. A current-state-only legacy project receives no automatic intermediate rows during schema migration.

Before the first new Runtime authority command, or during verified migration cutover, the allocator requires a current-boundary manifest. An existing trustworthy positive pointer R becomes the boundary R. A populated legacy project claiming revision 0 moves to boundary 1 and has no revision-0 manifest. The following command then becomes R+1. Pre-boundary integers remain unavailable rather than empty or inferred.

## Migration adapter

Legacy CIR import no longer increments revision per source event or chapter. A non-empty new target uses one boundary number; legacy events keep `applied_revision=NULL`. Import, scan, dry-run, verification and snapshot remain legacy workflow activity. Confirmed cutover computes the current projection hash, creates one `bootstrap`/`bootstrap_boundary` manifest in the same `BEGIN IMMEDIATE` transaction, then changes `authority_mode` without another story revision.

Bootstrap manifests bind existing finalized chapter artifacts where present. Other current-state domains are represented by the boundary state hash pending the later approved state-artifact/history implementation. This is an explicit Batch 1 compatibility foundation; it does not make pre-boundary history queryable and does not claim complete event coverage.

## Availability metadata

- Native: `history_completeness=native_complete`, available from 0, backfill not required.
- Legacy before boundary: `unavailable`, availability null, `manifest_backfill_required=1`.
- Boundary established: `bootstrap_boundary`, available from R for future governed capability, backfill not required.

Batch 1 still returns `HISTORY_NOT_IMPLEMENTED` for `at_revision`; availability metadata does not expose historical state.

Bootstrap provenance is confined to the boundary row. Later native commands retain their own stable command provenance and actor rather than inheriting compatibility labels.
