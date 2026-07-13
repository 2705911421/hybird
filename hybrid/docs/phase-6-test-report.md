# Phase 6 test report

Date: 2026-07-12

## Deterministic coverage

- Runtime Phase 6 observability/migration tests: 9 passed.
- Studio Runtime status/proxy tests: 10 passed.
- Core typecheck and build: passed.
- Studio client/server typecheck: passed.

Runtime coverage includes authentication, empty project, degraded/recovery state, commit cursor pagination/filter invalidation, bounded large event payloads, evidence/path redaction, nested secret redaction, absence of internal table names, configuration secret isolation, direct recovery, confirmation-required recovery, single-use job state, audit trail, and explicitly blocked snapshot restore.

Studio coverage includes Runtime unavailable, malformed DTO/version mismatch, database lock mapping, bearer server-side handling, no token leakage, pagination proxy, recovery confirmation forwarding, and recovery feature flag.

The complete suite, contract traversal, frontend component states, and deterministic Runtime/Studio E2E are run during final sign-off; final counts are recorded after those commands complete.
