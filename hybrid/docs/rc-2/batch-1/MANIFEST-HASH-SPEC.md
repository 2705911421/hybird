# Manifest Hash Specification

Logical version: `revision-manifest/v1`
Algorithm: SHA-256, stored as lowercase `sha256:{64 hex}`

## Canonical serialization

The logical manifest object excludes `manifest_id`, `manifest_hash` and physical database-generated identifiers. Strings and object keys are Unicode NFC. Object keys are sorted lexicographically. Arrays remain ordered. Integers are JSON numbers; null remains explicit and is distinct from empty arrays/strings. Serialization is UTF-8 JSON with `ensure_ascii=false`, no insignificant whitespace and non-finite numbers rejected.

Accepted timestamps participate in the hash and normalize to UTC RFC3339 with six fractional digits and `Z`. Ordered event IDs/hashes preserve ordinal order. Artifact reference/hash pairs sort by reference then hash before serialization. Hash algorithm tags participate in canonical data.

The logical fields are project/revision/predecessor, transition and command/commit/idempotency/request identities, event count/range and ordered membership, artifact membership, event/reducer/manifest/contract versions, provenance/actor, accepted timestamp and resulting state hash.

`manifest_id` is UUIDv5 over `project_id + NUL + revision + NUL + manifest_hash` under the frozen RC-2 namespace. `ordered_event_ids_hash` separately hashes the two ordered membership arrays and is checked by doctor.

## Required behavior

- Object field insertion order does not change the hash.
- Event order, artifact hash, predecessor hash, timestamp or any logical field change does.
- Retry returns the stored manifest and identical hash.
- Manifest tamper, previous-chain tamper, event envelope tamper and artifact mismatch are diagnosable.
- Native provenance/actor values participate unchanged in the hash; bootstrap compatibility provenance is used only for the boundary manifest.
