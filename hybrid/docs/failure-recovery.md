# Phase 4 failure recovery

Prepare or validate followed by process exit leaves an explicit `PREPARED` or
`VALIDATED` commit. Doctor reports it and the client retries with the original
idempotency key. There is no external body staging because bodies are SQLite
`TEXT`.

Failures after `BEGIN IMMEDIATE`, during event append, in a reducer, or before
finalize roll back artifact/events/projections/revision/outbox together. The
durable state remains `VALIDATED`; retry the identical commit. A successful
commit with a lost HTTP response is replayed from `FINALIZED` and returns the
same revision and event count. Concurrent commits serialize on SQLite and the
loser receives `REVISION_CONFLICT`; a lock timeout returns retryable
`DATABASE_LOCKED`.

Outbox failure does not affect authority. Doctor reports pending/failed outbox
rows; an operator reruns the worker. Projection mismatch is checked with a
dry-run replay and expected hash, then repaired by replaying from the append-only
event store. Runtime restart needs no file-state inference.

Doctor repair rules:

- `PREPARED`/`VALIDATED`: retry the original lifecycle request or call
  `POST /commits/recover` with `action=abort` and operator scope.
- `PERSISTING`/`COMMITTED`/`PROJECTING`/`RECOVERY_REQUIRED`: stop InkOS writes,
  inspect transitions and call `POST /commits/recover` with `action=recover`.
  Runtime removes non-final events, rebuilds core projections from FINALIZED
  events, and resubmits the stored validated artifact with its original key.
- projection hash mismatch: dry-run replay, compare hash, then operator replay.
- SQLite integrity failure: restore a verified database snapshot.
- Windows file occupation: canonical commit is unaffected; retry the failed row
  through `POST /outbox/run` or `story-runtime run-outbox`.

Unknown half-commits are prevented by the single SQLite transaction. Database
snapshots must include WAL state or be taken with SQLite backup/checkpoint
semantics.

## Fault matrix verification

The deterministic matrix covers exit after prepare, exit after validate, body
artifact failure, exit after transaction begin, mid-event failure, reducer
failure, failure before finalize, lost HTTP response, unexecuted outbox, SQLite
lock, Runtime restart, InkOS/client exit, concurrent same-chapter candidates,
same-revision sequence rejection, and Windows occupied-file replacement. Every
authority failure leaves an explicit durable state or rolls back to `VALIDATED`.
