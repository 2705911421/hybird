# Phase 5 test report

Date: 2026-07-12

Current verified gates:

- Story Runtime full suite: 57 tests passed before the cross-language contract additions; targeted shared-contract suite subsequently passed 6/6. A final full-suite recount remains required before Phase 5 sign-off.
- InkOS Core targeted review/security/persistence tests: 11 tests passed after shared-fixture coverage; Core typecheck and build passed.
- Studio Runtime review/status routes: 4 tests passed; Studio client/server typecheck passed after rebuilding Core.
- CLI and TUI changes typecheck passed.

Covered cases include strict schema parsing, unknown/missing/invalid enum/version, Python/TypeScript shared fixtures, artifact size/envelope/capability attacks, CJK and emoji code-point offsets, bad hash/stale evidence, finding deduplication, blocking and nonblocking status, decision/revision idempotency conflicts, re-audit enforcement, changed-span bounds, typed commit requirements, SQLite authority conflicts, Runtime-only persistence, lost-response retry, Studio filters/decisions, and legacy direct-write guards.

This report is intentionally not a final completion claim. Final sign-off still requires full Core/Studio/CLI suites, the deterministic Runtime E2E with unified review enabled, OpenAPI/schema traversal and a requirement-by-requirement completion audit.
