# Chapter commit state machine

Phase 4 uses one durable lifecycle per `(project_id, idempotency_key)`:

`PREPARED -> VALIDATED -> PERSISTING -> COMMITTED -> PROJECTING -> FINALIZED`.

Terminal alternatives are `REJECTED` and `ABORTED`; `RECOVERY_REQUIRED` is
reserved for an operator-visible recovery workflow. Every accepted transition
is inserted into `commit_transitions` with request, idempotency, project,
chapter, expected/resulting revision, schema version, reason, and UTC time.
`ChapterCommitService._transition` is the transition gate and rejects edges not
listed in `_ALLOWED_TRANSITIONS`.

Prepare changes no story fact. Validate stores the immutable artifact only
after deterministic schema, checksum, event, and evidence checks. A blocking
result transitions to `REJECTED`. Commit opens `BEGIN IMMEDIATE`, performs the
revision compare-and-swap, appends deterministic events, runs core reducers,
updates revision/latest chapter/checkpoints, finalizes the audit record, and
enqueues rebuildable side effects before the transaction commits.

The intermediate commit states are written inside that same SQLite transaction.
They are audit records in a successful commit, not externally observable partial
authority. A process or reducer failure rolls the entire commit transaction back
to durable `VALIDATED`. Retrying the same request resumes safely. A finalized
request returns the stored result and never applies events twice.

Illegal transitions return `ILLEGAL_STATE_TRANSITION`. Revision races return
`REVISION_CONFLICT`. Same-key/different-payload use returns
`IDEMPOTENCY_CONFLICT` or `ARTIFACT_CONFLICT`. SQLite lock errors are retryable
`DATABASE_LOCKED` failures.
