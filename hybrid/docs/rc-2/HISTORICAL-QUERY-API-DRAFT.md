# Historical Query API Draft

Status: design only; no route or client implementation is authorized in RC-2A.

## Uniform historical contract

For every endpoint, `at_revision=R` means the authoritative project state after revision R completed and before revision R+1 began. All domains use the same revision resolver, history-availability boundary, event/reducer compatibility rules and authorization. No endpoint may silently use latest because its domain lacks history support.

Every successful historical response includes:

```json
{
  "project_id": "book-1",
  "at_revision": 42,
  "current_revision": 57,
  "contract_version": "story-runtime/v2",
  "event_schema_version": "story-events/v1",
  "reducer_version": "story-reducers/v1",
  "state_hash": "sha256...",
  "snapshot_token": "opaque-read-token",
  "history": {
    "available_from_revision": 12,
    "complete": true,
    "migration_boundary": 12
  },
  "provenance": {
    "revision_manifest_id": "...",
    "source": "native|verified-import|bootstrap-boundary"
  },
  "data": {}
}
```

`snapshot_token` is an opaque, signed read-consistency cursor binding project, revision, authorization subject, filters, contract/event/reducer versions and expiry. It is not a filesystem snapshot path and grants no authority beyond the caller's current permission.

## Endpoints

### `GET /projects/{id}/revisions`

Lists existing revision manifests, never inferred integer ranges.

Query: `cursor`, `limit` (default 50, max 200), optional `from_revision`, `to_revision`, `kind`. Items include revision, transition kind, commit/command ID, event count/range, manifest hash, actor class, provenance class, schema/reducer versions, timestamp and history availability flags. Payload/evidence is not embedded.

### `GET /projects/{id}/state?at_revision=`

Returns a bounded aggregate state manifest plus optionally selected domains. Query supports `include=entities,relationships,facts,resources,timeline,threads,foreshadowing,summaries`; default is counts/hash/metadata only. Full collections must be paged through their domain endpoints. A response must not exceed the configured item/byte limit.

### `GET /projects/{id}/entities/{entity_id}?at_revision=`

Returns the entity version effective at R, including `valid_from_revision`, `valid_to_revision`, source event ID and tombstone state. If it did not yet exist, return `404 ENTITY_NOT_FOUND_AT_REVISION`; if it was deleted, authorized callers may receive a minimal tombstone envelope rather than deleted sensitive attributes.

### `GET /projects/{id}/relationships?at_revision=`

Filters: entity, type, status, cursor, limit. Each item includes validity interval, source event and tombstone metadata. Both endpoints must be checked for project scoping; cross-project entity IDs cannot join.

### `GET /projects/{id}/threads?at_revision=`

Filters: `status`, `kind=thread|foreshadow`, chapter range, cursor, limit. Lifecycle values must be versioned contract enums, not free-text interpretation.

### `GET /projects/{id}/timeline?at_revision=`

Orders by stable narrative sequence key plus identity. Cursor binds target revision and sort. Reordered items preserve prior versions rather than mutating history.

### `GET /projects/{id}/diff?from_revision=&to_revision=`

Returns changes grouped by aggregate kind and identity: created, changed, tombstoned and restored. Default is metadata/field paths and hashes. Large body or value payloads require explicit `include_values=true` plus stricter limits. Diff is directional; `from_revision <= to_revision`. Both revisions must be available under the same public semantics even if internal reducers differ.

### `POST /projects/{id}/projections/replay`

Creates an asynchronous replay job. Example body:

```json
{
  "idempotency_key": "...",
  "target_revision": 42,
  "projection_set": "core/v1",
  "mode": "verify|repair",
  "dry_run": true,
  "expected_event_schema_version": "story-events/v1",
  "expected_reducer_version": "story-reducers/v1",
  "expected_state_hash": "..."
}
```

Rules:

- `verify` and all `dry_run` operations use an isolated temporary read model;
- target revision replay never replaces latest tables;
- `repair` may atomically replace only the latest projection after hash verification and explicit authorization;
- event store and project revision are read-only;
- unknown event/schema/reducer versions fail closed;
- response is `202` with a job ID; per-project concurrency and cost quotas apply.

### `GET /projects/{id}/replay-jobs/{job_id}`

Returns queued/running/succeeded/mismatch/failed/cancelled, target revision, progress event sequence, versions, hashes, counts, timing, bounded diagnostics and whether any atomic latest-projection swap occurred. It never returns raw DB paths or full payloads.

### `GET /projects/{id}/revision/{revision}/manifest`

Returns the immutable transition manifest: revision, previous revision/hash, command kind/id, commit ID if any, ordered event IDs/hashes, event range, artifact references/hashes, provenance class, schema/reducer versions, timestamp and signature/hash. Sensitive actor identity is policy-filtered.

## Pagination and consistency

- Cursor pagination only; no mutable offset pagination.
- Default page 50, max 200 for state domains; revisions max 200; event/evidence expansion max 100.
- Cursor/snapshot token is invalid if used with another project, revision, authorization subject, filter, sort or version.
- Latest query without `at_revision` resolves latest exactly once and returns a token. Follow-up pages use that fixed revision even if a new commit finalizes.
- Tokens expire, but the underlying revision remains queryable if retention allows; clients can restart from revision plus filters.

## Error semantics

| HTTP / code | Meaning |
| --- | --- |
| 400 `REVISION_RANGE_INVALID` | malformed or reversed range |
| 401/403 | authentication/authorization failure; no project existence detail |
| 404 `PROJECT_NOT_FOUND` | authorized subject cannot access a project |
| 404 `REVISION_NOT_FOUND` | revision manifest never existed, including future revision |
| 404 `*_NOT_FOUND_AT_REVISION` | aggregate not effective at R |
| 409 `HISTORY_UNAVAILABLE` | R precedes honest bootstrap/migration boundary; include earliest available revision |
| 409 `EVENT_SCHEMA_INCOMPATIBLE` | stored event cannot be read by installed schema adapters |
| 409 `REDUCER_VERSION_INCOMPATIBLE` | required deterministic reducer unavailable |
| 410 `HISTORY_PRUNED` | authorized retention policy intentionally removed required payload; include manifest/hash proof where allowed |
| 413 `RESPONSE_TOO_LARGE` | requested expansion exceeds limits |
| 429 `HISTORICAL_QUERY_QUOTA_EXCEEDED` | replay/query cost or concurrency limit reached |

Missing revision, unavailable history and pruned history are distinct. A migration must never convert `HISTORY_UNAVAILABLE` into a fabricated 200 response.

## Migration boundary

Each project exposes `history_available_from_revision` and `history_completeness`:

- native complete: all revisions reconstructible;
- verified imported history: reconstructible from the first verified source transition;
- bootstrap boundary: only the imported current state at the boundary and later native revisions are available;
- manifest-only/pruned: revision exists but some payload is unavailable.

Cross-boundary diff is rejected unless both endpoints have comparable complete state. A special metadata-only diff may report “bootstrap boundary introduced current state” without pretending to know prior values.

## Tombstones

Deletion is an event and a new project revision. Historical queries before deletion return the prior value; at/after deletion return a policy-filtered tombstone or not-found. Tombstones contain identity hash, deletion revision, event/provenance reference and retention classification, never automatically retain sensitive deleted prose.

## Authorization, privacy and abuse controls

- Re-authorize the project and data classification on every request and page; old tokens do not preserve revoked access.
- Apply current access policy to historical data; historical existence is not a permission bypass.
- Separate permissions: `history:read`, `history:sensitive-read`, `replay:verify`, `projection:repair`.
- Rate-limit by caller and project; cap revision span, event count, response bytes, simultaneous jobs and wall time.
- Cache only authorization-safe, version-keyed results; encrypted storage for snapshots/history containing prose.
- Redact migration paths, credentials, local filesystem metadata and deleted sensitive values from manifests/jobs.
- Return uniform unauthorized responses to prevent project/revision enumeration.

## TypeScript and UI contract direction

Generate/validate strict TypeScript schemas for the envelope, manifest, domain pages, diff and replay jobs. Studio/CLI/TUI may consume only the HTTP client; none may read Runtime SQLite or local Markdown to fill historical gaps. UI work begins only after Runtime semantics and client contracts pass RC-2 gates.
