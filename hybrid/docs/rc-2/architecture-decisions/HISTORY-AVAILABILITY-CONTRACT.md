# History Availability Contract

Status: **Frozen / Accepted 2026-07-15**
Contract family: `history-availability/v1`

## Required fields

Every project status, revision list item and historical response envelope contains:

```text
history_available_from_revision: integer | null
history_completeness: native_complete | verified_import | bootstrap_boundary | manifest_only | pruned | unavailable
history_boundary_kind: none | verified_import | bootstrap_boundary | retention_prune | compatibility
history_pruned_before_revision: integer | null
history_payload_availability: full | metadata_only | tombstone_only | pruned | unavailable
history_boundary_reason: stable code
migration_provenance_id: string | null
```

Semantics:

| Completeness | Meaning |
| --- | --- |
| `native_complete` | authentic Runtime lineage is reconstructible from native revision 0 |
| `verified_import` | authentic imported boundary/transitions are evidenced from the declared earliest revision |
| `bootstrap_boundary` | one full current state becomes authority at R; earlier state is unknown |
| `manifest_only` | revision identity/hash exists, but requested state payload is not retained/available |
| `pruned` | approved retention removed payload; manifest/hash proof remains |
| `unavailable` | no authoritative state payload can be served under installed compatibility/policy |

`history_pruned_before_revision` is the greatest exclusive lower payload boundary imposed by retention; it does not erase manifests or imply that every later revision is available.

## API behavior

- Successful history returns the availability block at top level with effective/current revision, manifest ID/hash, event/reducer versions, state hash and provenance.
- R before an honest boundary: `409 HISTORY_UNAVAILABLE` and safe `available_from_revision`/reason.
- R has no manifest, including future: `404 REVISION_NOT_FOUND`.
- Retained manifest but pruned required payload: `410 HISTORY_PRUNED`.
- Entity absent at an otherwise available R: `404 ENTITY_NOT_FOUND_AT_REVISION`; do not confuse it with unavailable project history.
- Diff requires both endpoints with comparable payload. Otherwise `409 HISTORY_COMPARISON_UNAVAILABLE`; metadata-only boundary information may be returned explicitly, never a fabricated structural diff.
- Latest without `at_revision` uses latest service. Historical endpoints still expose availability and never fall back to latest.

## Product behavior

- Project status shows earliest available revision, completeness, boundary reason and redacted migration provenance.
- Studio shows a persistent read-only historical banner and disables all writes at historical R; unavailable/pruned states are distinct.
- CLI prints stable codes and the earliest available revision to stderr, exits non-zero, and never retries against latest.
- TUI shows classification/boundary next to the revision selector and cannot enter edit mode for historical state.

## Tokens, authorization and retention

Historical snapshot/cursor tokens are opaque, signed and bind subject, project, revision, filters/sort, contract/event/reducer versions, payload classification and expiry. They are not snapshot paths and do not survive authorization revocation. Every page reauthorizes current `history:read`; sensitive values require `history:sensitive-read`. Uniform unauthorized responses avoid existence leakage.

Retention policy is explicit, project/data-class aware and auditable. It may prune payload/artifacts but not rewrite manifests/events headers/hashes. Pruning updates an append-only availability/retention record, invalidates relevant tokens/caches, and changes future queries to `HISTORY_PRUNED`. Encrypted snapshots and caches cannot outlive the governing permission/retention period.

## Migration behavior

Migration chooses a classification before cutover, persists it atomically with the boundary manifest and provenance, and never upgrades completeness based on row count or partial events. The classification may become more restrictive after corruption/retention; any more permissive lineage requires separately verified immutable evidence and the legacy-compatibility rules—never manifest rewrite.
