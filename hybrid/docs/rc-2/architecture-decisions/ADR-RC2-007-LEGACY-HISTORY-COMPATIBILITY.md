# ADR-RC2-007: Legacy History Compatibility

- Status: Accepted
- Decision: **APPROVED**
- Date: 2026-07-15

## Classification rules

### Native current projects

Classify as `native_complete` from 0 only when every finalized revision has a valid manifest, closed-catalog events/artifacts, contiguous ordinals and compatible reducers, including a genuine empty revision 0. Otherwise classify complete from the first valid manifest only when the preceding state is independently represented by a verified boundary artifact; absent that proof, bootstrap the current authoritative state at current R (or R=1 for non-empty revision 0).

### Legacy migrated projects

Default to `bootstrap_boundary`: pre-boundary unavailable, source provenance retained, existing public/project numbering not rewritten, and no row/chapter count is treated as an atomic transition. Authority cutover and bootstrap finalization are linked but not counted twice.

### Projects with partial events

- A verified prefix is useful provenance but does not make later state reconstructible. Public availability may be `verified_import` only for the contiguous verified range and must stop before the first gap; continuing current state requires a separate bootstrap boundary and explicit discontinuity.
- `complete from R` is allowed when a full boundary state at R plus every later transition is verified. Earlier history remains unavailable.
- `applied_revision=NULL` events are never assigned a revision by inference. A deterministic adapter may promote them only with external proof of command boundary/order; otherwise they are provenance-only.
- Arbitrary old event types are quarantined outside the authority stream unless a closed, versioned adapter produces a canonical event with evidence and stable hashes.
- Legacy adapter interpretation is allowed only as a pure, deterministic, versioned migration step. Adapter output is validated by the current catalog and its mapping/provenance hashes are retained.

## Immutability and cutover

Imported manifests are immutable after finalize. Re-import with the same source/mapping hashes is idempotent; changed source creates a new migration attempt and cannot rewrite accepted history. Rollback before cutover restores the verified target snapshot. After authoritative manifests are used, rollback disables writes/restores a compatible whole-DB snapshot without deleting newly accepted events; code downgrade is blocked when schema/reader compatibility is absent.

## User-visible result

Every project status states classification, available-from revision, boundary reason and migration provenance. Old projects may remain limited indefinitely. No product surface may turn partial events, Markdown, CIR rows, migration audit or idempotency records into story revisions.
