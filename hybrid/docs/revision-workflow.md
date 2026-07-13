# Revision workflow

Runtime-authority chapters follow one closed loop:

1. InkOS Writer produces a candidate body.
2. InkOS produces an inert `StateMutationProposal` and one or more `ChapterReviewArtifact` objects.
3. `POST /reviews/validate` validates scope, revision, body hash, evidence and fingerprints, then stores the raw artifacts.
4. If status is blocked, stale, rejected or changes-requested, the chapter cannot reach commit. Human review or revision is required.
5. InkOS creates a `RevisionPlan` from the effective findings. It includes allowed scope, forbidden hard facts, user-locked spans and `requires_reaudit=true`.
6. Reviser returns candidate prose. `InkOSRevisionAdapter` emits a `RevisionResult`; updated state/ledger/hooks from the model are never authority writes.
7. `POST /revisions/validate` checks scope, revision and hashes, verifies changed spans, stores the result and invalidates prior evidence.
8. InkOS re-extracts a proposal and reruns affected reviewers against the revised body.
9. Runtime validates the replacement artifacts. Required human decisions are posted idempotently to `/reviews/decisions`.
10. Only then may the existing prepare/validate/commit lifecycle run. Commit independently rechecks the effective review gate.

The prohibited shortcut is revision followed by direct commit without re-extraction and re-audit. `unifiedReview.enabled=false` restores display mapping for legacy review flow but does not return authority to Truth, delete typed artifacts, or permit two effective human-decision stores for one Runtime chapter.

## Human decisions

Blocking continuity conflicts, major foreshadowing deletion, character life/death, core relationship or world-rule changes, broad rewrites, low-confidence entity disambiguation and severe reviewer disagreement require a human decision. Decisions are tied to `source_revision`; stale decisions never apply to a newer revision. Duplicate idempotency keys replay only identical payloads.

## Failure behavior

Malformed Agent output is an explicit parse/schema error. A stale hash or revision returns conflict. Invalid evidence produces stale review status and blocks commit. A malformed Reviser result is rejected. A changed body with no new matching review remains unreviewed. Runtime APIs never attempt to repair model JSON or invoke another model.
