# Compatibility Notes

Manifest fields are never silently null for compatibility. Batch 1 writes:

- `manifest_schema_version=revision-manifest/v1`;
- `contract_version=story-runtime/v1`;
- current unclosed events as `event_schema_version=legacy-unversioned`;
- native legacy reducers as `story-reducers/legacy-v1`;
- initialization/bootstrap reducers as `story-reducers/not-applicable`;
- explicit provenance `native` or `bootstrap_boundary`.

Unknown/empty compatibility data is a doctor failure. Batch 1 does not define the closed event catalog, payload schemas or versioned reducer registry; those remain Batch 2 prerequisites.

The existing `at_revision` parameter now fails closed with `409 HISTORY_NOT_IMPLEMENTED`. Latest-only reads remain unchanged. This prevents manifests from disguising a current projection as historical state and is not a historical query implementation.

Scoped operator append remains a compatibility transport, but it can no longer bypass the allocator/manifest transaction. Its arbitrary event vocabulary is not described as formal domain coverage. Batch 2 must close and validate that vocabulary.

Replay behavior is retained for regression compatibility and remains revision-neutral. Batch 1 does not claim the approved isolated verify/latest-only repair implementation is complete.
