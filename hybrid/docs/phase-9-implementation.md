# Phase 9 implementation

Implemented in this phase:

- Schema 7 scale indexes and FTS5 trigram retrieval; fact filtering moved into SQLite without skipping revisions or validators.
- WAL synchronous/checkpoint/journal caps, read-only connection API, network filesystem warning and explicit checkpoint CLI.
- JSON structured request logs with request ID, masked project ID, operation, duration, result, retryability, error/version/schema fields, redaction and rotation.
- Online snapshot manifest/checksum/logical projection hash and safe new-directory restore with deep doctor; compatibility and pre-snapshot migration report commands.
- Deterministic scalable Chinese corpus, million benchmark, short/24h soak harness and raw Windows evidence.
- Runtime process lifecycle with port discovery, version/schema handshake, random token environment transfer, single PID/stale cleanup, POSIX group signaling, graceful stop and capped restart backoff.
- Cross-platform Python/Node matrices, offline/package smoke, deterministic Studio E2E benchmark, audits, secret scan, SBOM and release workflows.
- Studio Runtime navigation and runaway polling defects fixed based on Playwright measurement.
- NOTICE, upstream synchronization, packaging, capacity, operations, backup, compatibility, security and release documents.

No new domain model, database, distributed authority, Runtime or required real model dependency was introduced.

Phase 9 is not complete: see the test report and release checklist for environment evidence and packaging blockers.
