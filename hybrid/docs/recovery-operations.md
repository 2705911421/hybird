# Recovery operations

## Direct after preview

| Operation | Authority impact | Notes |
| --- | --- | --- |
| refresh | none | browser/server read only |
| rerun doctor | none | deep mode only on explicit request |
| `retry_outbox_item` | none | retries one disposable side effect |
| `rebuild_lexical_index` | none | rebuilds FTS from Runtime-owned retrieval documents |
| `rebuild_vector_index` | none | reports `not_configured` when no vector provider exists |
| diagnostic report | none | JSON download, always redacted |

## Confirmation required

| Operation | Guard |
| --- | --- |
| `replay_core_projection` | preview + one-time confirmation token + current revision check |
| `abort_prepared_commit` | PREPARED/VALIDATED only; transition is audited |
| `restore_snapshot` | previewed but blocked until a verified authoritative snapshot provider exists |
| `clear_retry_queue` | removes failed disposable outbox entries only |
| `resume_interrupted_migration` | preview + confirmation; uses the migration engine |

Confirmation tokens are returned only by preview, stored hashed, consumed once, and never logged. A job whose state changed cannot be executed with a stale confirmation.

## Never exposed

Deleting authority events, deleting finalized commits, changing revision/facts directly, arbitrary SQL, validation bypass, forced expected-revision overwrite, and direct fact-table edits have no API or UI operation.

## Cancellation

Cancellation is accepted only when a running job declares `cancellable=true`. Current synchronous operations cross their safe boundary immediately and therefore report `cancellable=false`; cancel requests return a typed conflict instead of interrupting a transaction.

## Audit

Every preview, execution, completion/failure, and safe cancellation writes an immutable audit entry with job, project, actor, outcome, redacted details, and timestamp. The Studio history view reads this public DTO, not the database.
