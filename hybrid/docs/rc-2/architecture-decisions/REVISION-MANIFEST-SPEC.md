# Immutable Revision Manifest Specification

Status: **Frozen / Accepted 2026-07-15**
Logical schema version: `revision-manifest/v1`

## Purpose and authority

The manifest is authority for whether a project revision exists, its predecessor, atomic command boundary, ordered event/artifact membership, versions, integrity and provenance. It is not authority for domain field values; events and referenced immutable artifacts provide those values. A finalized manifest is append-only and never updated.

## Required fields

| Field | Rule |
| --- | --- |
| `manifest_id` | deterministic ID derived from project/revision/manifest hash domain; globally unique |
| `project_id` | owning project |
| `revision` | non-negative; unique with project |
| `previous_revision` | `revision-1` after lineage start; null for native revision 0 or a bootstrap lineage start |
| `previous_manifest_hash` | exact predecessor hash or null at lineage start |
| `transition_kind` | closed enum: `initialize_empty`, `chapter_finalize`, `chapter_replace`, `domain_command`, `bootstrap`, `verified_import`, `compensation`, `tombstone`, `restore` |
| `command_id` | deterministic command identity; required and project-unique |
| `commit_id` | chapter commit identity when applicable; null otherwise |
| `idempotency_key` | required; unique per project/operation namespace and bound to request hash |
| `event_count` | positive except native revision 0 |
| `first_event_sequence`, `last_event_sequence` | inclusive project-stream bounds; both null only for revision 0 |
| `ordered_event_ids` | canonical array in ordinal order |
| `ordered_event_hashes` | canonical envelope hashes in matching order |
| `artifact_references` | typed stable IDs/URIs without local path leakage |
| `artifact_hashes` | algorithm-tagged hashes aligned with references |
| `event_schema_version` | catalog/envelope compatibility identifier |
| `reducer_version` | reducer-set identifier required to reproduce state hash |
| `schema_version` | manifest/storage logical schema version |
| `provenance_class` | `native`, `verified_import`, `bootstrap_boundary`, `compensation` |
| `provenance_id` | immutable provenance ledger reference |
| `actor_class` | policy-safe class, not necessarily personal identity |
| `created_at` | accepted command timestamp, UTC normalized |
| `state_hash` | canonical state hash after this transition |
| `manifest_hash` | canonical hash specified below |

Implementations may add `payload_schema_versions`, `history_boundary_kind`, `source_revision` and signatures, but they participate in canonical hashing.

## Canonical hash

1. Build the manifest object without `manifest_id`, `manifest_hash` and database-generated physical sequence fields not listed in the logical contract.
2. Normalize strings to Unicode NFC, timestamps to UTC RFC3339 with fixed precision, integers as JSON numbers, null explicitly, and hashes as lowercase algorithm-prefixed strings.
3. Preserve ordered arrays; sort object keys lexicographically by Unicode code point; serialize as canonical UTF-8 JSON with no insignificant whitespace.
4. Compute `manifest_hash = sha256(canonical_bytes)` and `manifest_id = UUIDv5(RC2 manifest namespace, project_id + NUL + revision + NUL + manifest_hash)` (or an equivalently frozen deterministic ID algorithm before Batch 1 code merge).
5. Recalculation must produce the stored value byte-for-byte. Any mismatch is corruption.

Event envelope hashes cover every envelope field except storage sequence; payload hashes cover canonical payload only. Artifact hash algorithms are explicit.

## Range and continuity

- Events belonging to one manifest must be contiguous in that project's logical event stream and have ordinal `0..event_count-1`.
- Physical global SQLite sequences may contain other projects between them; therefore the authoritative continuity check is ordered project-local event IDs/ordinals. `first/last_event_sequence` are acceleration/audit bounds and any range scan must exactly match the ordered arrays.
- Zero-event story revisions are prohibited. The sole zero-event manifest is native `initialize_empty` revision 0. Bootstrap has exactly one bootstrap event; ordinary commands have at least one typed event.
- Native lineage begins at revision 0. Bootstrap lineage may begin at R>0 with null predecessor and explicit boundary fields. This does not imply revisions 0..R-1.

## Chapter, migration and idempotency links

- A finalized chapter manifest references one finalized `chapter_commits.commit_id`, the immutable artifact/body hash, summary artifact/hash and all ordered state events including mandatory `chapter.finalized`.
- Migration provenance links source checksum set, adapter/mapping versions, authority cutover audit and verified/bootstrap classification. Local paths are redacted from public views.
- `(project_id, command_id)` and the operation-scoped idempotency key are unique. A retry must match stored request hash and returns the existing manifest. A conflicting reuse fails.

## Atomic finalization

Within one `BEGIN IMMEDIATE` transaction: lock/compare latest pointer; validate command and idempotency; append typed events/artifacts; reduce current/history; calculate state and manifest hashes; insert finalized manifest; compare-and-swap the latest project pointer; record idempotency result; commit. No finalized row is mutable. An aborted transaction publishes nothing and does not consume a revision.
