# Canonical Import Format

`canonical-import/v1` is the sole Phase 7 input to Runtime import. Its normative JSON Schema is [`../contracts/schemas/canonical-import-v1.json`](../contracts/schemas/canonical-import-v1.json).

## Required sections

- `source_metadata`: source kind, source path fingerprint, mapping version, scan time.
- `project`: target-independent project identity and extensions.
- `chapters`: chapter number, title, Unicode body, normalized body SHA-256, source SHA-256 and source path.
- `entities`, `aliases`, `relationships`, `facts`, `events`, `timeline`, `narrative_threads`.
- `reviews`, `summaries`, and rebuildable `documents`.
- `unresolved_conflicts` and `unmapped_fields`.
- `provenance`: stable CIR item ID to source path/checksum/locator/kind/confidence.

Every importable item has a UUIDv5 `cir_item_id` derived from source fingerprint, item kind and stable locator/content checksum. Repeating the same source, mapping version, and target therefore reuses a job and cannot duplicate an imported item.

Unknown fields are retained in `unmapped_fields`, item attributes, document metadata, or provenance. A mapper must not invent missing timeline entries or silently discard unsupported fields. `vectors.db` contributes only rebuildable document metadata; embeddings are never authoritative.

## Lifecycle use

CIR is persisted on the migration job before target writes. It supports schema validation, dry-run, conflict review, retry, audit, target-schema changes and future source adapters. Source-specific mappers never write authority tables directly.

Dry-run, import and independent replay all consume the same effective-CIR resolver. Human choices therefore select or exclude the actual candidate items; they are not audit-only annotations.
