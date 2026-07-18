# RC-2B1D2 Missing-Revision Semantics

## State model

| State | Meaning |
|---|---|
| `VALID` | The row, predecessor, compatibility, hashes, provenance, event membership and artifacts are verified. |
| `DIRECTLY_CORRUPTED` | The present revision has a local integrity or provenance defect. |
| `MISSING_REVISION` | A logical revision expected by the stored sequence or project pointer has no manifest row. |
| `MISSING_PREDECESSOR` | A present row has a malformed predecessor pointer without a numeric row gap. |
| `AFFECTED_BY_MISSING_REVISION` | A present row follows a missing logical revision. |
| `AFFECTED_BY_PRIOR_CORRUPTION` | A present row follows a directly corrupted or unverifiable row. |
| `UNVERIFIABLE_UNKNOWN_VERSION` | Unknown compatibility prevents deterministic verification. |
| `ORPHAN_MANIFEST` | A manifest is ahead of the project's current revision pointer. |

Missing revisions are logical diagnostic nodes. Doctor never inserts, repairs, or
copies state into them. A bootstrap boundary is the first expected revision of a
limited-history lineage, so pre-boundary integers are not gaps.

## Precedence

A local defect on a present row wins over downstream context. Thus a corrupted R4
after missing R2 is `DIRECTLY_CORRUPTED`, while R3 is
`AFFECTED_BY_MISSING_REVISION`. Unknown compatibility similarly remains
`UNVERIFIABLE_UNKNOWN_VERSION`. The impact summary retains the missing ranges and
direct-corruption list so both facts remain visible.

## Summary contract

`MANIFEST_CHAIN_IMPACT` reports latest trusted, first untrusted, first missing,
missing ranges, direct corruptions, downstream ranges, affected count, project
current revision, latest manifest revision, and terminal state. The OpenAPI
Doctor contract includes these fields and all chain states.

## Verified cases

Automated tests cover a single gap, multiple gaps, missing latest, project behind,
direct corruption after a gap, unknown version after a gap, missing first native
revision after a valid boundary, and a fully valid chain. Existing corruption,
provenance, hash, compatibility and downstream tests remain active.
