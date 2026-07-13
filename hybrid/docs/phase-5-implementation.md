# Phase 5 implementation

Phase 5 unifies chapter review, revision and state extraction for Runtime-authority projects under `review-artifacts/v1`. Story Runtime remains the only canonical writer; InkOS remains the creative LLM host.

## Runtime

Migration 4 stores immutable review artifacts/findings, aggregate fingerprints, revision-bound human decisions, revision results and operation-level idempotency. Strict Pydantic contracts mirror the canonical JSON Schema. `ReviewService` validates scope, revision, body hash, Unicode evidence, artifact size, duplicate identity and idempotency before storage.

Commit validation requires typed review and `StateMutationProposal` objects when `unifiedReview.enabled` is true. SQLite-backed deterministic rules cover relationship entities, fact CAS, unexplained resurrection/location changes, world rules, resource underflow, timeline order and major foreshadowing changes. The final commit transaction rechecks matching review/body/revision, stale evidence, human reject/request-changes state and unresolved blocking fingerprints.

Runtime exposes `/reviews/validate`, `/reviews/decisions`, chapter reviews/status and `/revisions/validate`. It does not import or invoke an LLM.

## InkOS

`InkOSReviewAdapter`, `InkOSRevisionAdapter`, `RuntimeReviewClient` and `ReviewArtifactMapper` centralize the boundary. Model artifacts pass the controlled untrusted JSON parser and strict Zod schemas. Runtime chapter persistence validates the review before prepare and sends an inert typed proposal; it never invokes legacy chapter/Truth callbacks.

Studio exposes filtered review data and revision-bound decision routes, separates deterministic findings from literary suggestions, preserves evidence offsets/stale status and limits bulk decisions to non-blocking findings. CLI approval/rejection uses Runtime decisions for Runtime-authority books and refuses authority-changing bulk approval. TUI shows the same mapped Runtime review state on the active pending chapter. Legacy projects retain their existing filesystem/index flow.

## Rollback

`unifiedReview.enabled=false` disables typed review consumption and the Runtime commit review gate while preserving Story Runtime chapter authority. Typed rows are retained. Runtime-authority projects never resume Truth writes, and Studio/CLI continue rejecting direct authority mutations.

## Files

- Contract: `contracts/schemas/review-artifacts.json` and request schemas.
- Python: `story_runtime.contracts`, `story_runtime.reviews`, migration 4 and commit gate.
- TypeScript: `review-artifacts/*`, `story-runtime/client.ts`, chapter persistence port.
- Interfaces: Studio review routes, CLI review commands and TUI review notice.
- Architecture: ADR-009, review artifact spec and revision workflow.
