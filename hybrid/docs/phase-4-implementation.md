# Phase 4 implementation

Story Runtime is the sole writer for new Runtime-authority long-form projects.
Migration 3 adds authority metadata, durable chapter commits/artifacts and
transitions, deterministic event metadata, outbox rows, replay jobs, and richer
projection checkpoints. Chapter bodies use SQLite `TEXT` so the authority
transaction has no external blob failure window.

The enabled APIs are project creation, chapter prepare/validate/commit,
operator-scoped event append, projection replay, finalized chapter query, and
doctor. Contracts live in `contracts/story-runtime.openapi.yaml` and the JSON
Schema directory.

InkOS selects `LegacyChapterPersistence` or
`StoryRuntimeChapterPersistence` from project authority. The Runtime adapter
maps Writer/Auditor/state-delta output to a typed artifact, validates it, commits
it with revision CAS, and retries a lost-response unavailable error. Runtime
projects bypass legacy Truth validation/persistence and reject direct mutation
surfaces. Legacy projects retain their existing behavior.

Rollback and recovery are documented separately. Phase 4 does not migrate old
projects, run creative LLMs in Runtime, implement external blob storage, or
start later migration phases.

The production recovery surface includes operator-scoped
`POST /commits/recover`, `POST /outbox/run`, and the `run-outbox` CLI command.
The outbox worker builds Markdown, search, and JSON snapshot projections. File
outputs use same-directory temporary files plus atomic replace; failed rows keep
retry count and error details and never roll back canonical commits.
