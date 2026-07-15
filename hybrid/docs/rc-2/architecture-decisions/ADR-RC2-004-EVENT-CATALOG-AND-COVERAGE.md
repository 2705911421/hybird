# ADR-RC2-004: Closed Event Catalog and Coverage Gate

- Status: Accepted
- Decision: **APPROVED**
- Date: 2026-07-15

## Gate decision

Batch 2 event coverage correction is mandatory before Batch 3 can claim complete reducers and before any public historical query is published. Batch 1 may establish revision/manifest mechanics, but no historical result may be exposed from partial events.

## Minimum closed catalog

The first catalog version must include typed transitions for:

- `chapter.finalized` and authoritative chapter replacement;
- entity create/update/tombstone/restore;
- relationship create/update/tombstone/restore;
- fact assert/retract;
- resource adjust/set/tombstone;
- timeline create/update/tombstone;
- thread open/advance/defer/resolve/reopen;
- foreshadow introduce/reveal/resolve;
- world rule assert/change/retract;
- alias merge/resolve;
- project bootstrap boundary and verified-import transition;
- compensating story change.

Every catalog entry fixes aggregate, allowed transition, payload schema, evidence requirements, reducer family/version, tombstone/recreate policy and deterministic hash canonicalization. Event type is a closed versioned enum. Operator append remains an administrative transport only: it may append catalog-valid typed events after command-level authorization and invariant validation; arbitrary event type, aggregate or payload is rejected. Observational notes that are not story authority belong in a separate audit/provenance log.

## Required envelope

Every authority event contains:

`event_id`, `project_id`, `revision`, `ordinal`, `event_type`, `event_schema_version`, `payload_schema_version`, `aggregate_type`, `aggregate_id`, `reducer_family`, `reducer_version`, `command_id`, `commit_id` when applicable, `causation_id`, `correlation_id`, `actor_class`, `provenance_id`, typed `evidence`, deterministic `timestamp`, canonical payload and `payload_hash`.

`event_id` is deterministically derived from project, command/commit identity, revision, ordinal, type and payload hash. Timestamp is supplied by the accepted command envelope and persisted; reducers never read current time.

## Validation and ordering

- Ordinals are zero-based, unique and contiguous within one revision; manifest order must equal ordinal order.
- Event sequences for one finalized manifest are contiguous in the project stream. Global SQLite sequence gaps caused by other projects are irrelevant.
- Duplicate event ID is idempotent only when the complete canonical envelope hash matches; otherwise it is corruption.
- Logical duplicates use command/idempotency identity and aggregate transition invariants. They return the prior committed result or fail; reducers do not apply them twice.
- Unknown event type, aggregate, event schema, payload schema, reducer family or reducer version fails closed. Nothing is silently skipped or coerced to facts.
- Invalid transitions, out-of-order ordinals and reducer mismatch abort the entire authority transaction.

## Append-only, deletion and retention

Finalized authority events cannot be updated or deleted by normal application, replay, recovery, migration rollback or project deletion. Project deletion creates a project tombstone/retention transition and removes access/current projections according to policy; it does not cascade-delete the event stream. Recovery corrects derived data or appends compensation, never deletes authority events.

Retention may prune sensitive payload/artifact bytes only under an approved policy and immutable pruning manifest that retains hashes, event headers, reason, actor, time and affected range. Pruning is never represented as successful reconstructible history.

## Legacy inputs

Arbitrary old events are not silently admitted to the closed catalog. A versioned, deterministic adapter may promote an old event only when type, aggregate, payload and order can be proven. Otherwise it is quarantined as provenance-only source material and the project uses a bootstrap boundary.
