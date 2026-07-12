# Known differences and deliberate Phase 1 gaps

This list is scope control, not an implementation backlog for the current commit.

1. **No InkOS takeover or adapter.** InkOS continues to own its current writing workflow and truth files. Runtime client/shadow reads begin in Phase 2.
2. **No HTTP writes.** Prepare, validate, commit, event append, projection replay, import migration, and snapshot export routes exist for contract compatibility but return `403 WRITE_FEATURE_DISABLED` after DTO validation.
3. **Fixture bootstrap is CLI-only.** It is deterministic and idempotent, but it is not a general InkOS/webnovel import path. Real migration is Phase 7.
4. **RAG is local and deterministic.** Phase 1 uses lexical scoring over a rebuildable SQLite retrieval projection. It makes no embedding/rerank/LLM request. Vector and hybrid RRF providers remain future adapters.
5. **Read surface is intentionally narrow.** Exact entity lookup and governed context expose the approved DTOs. Specialized paginated relationship/event/timeline/thread/summary endpoints are deferred until a contract is approved.
6. **No chapter blob store or commit coordinator.** DTOs and authority schema reserve the boundary, but transactional chapter writes belong to Phase 4.
7. **Projection recovery is observable, not executable over HTTP.** Doctor returns an explicit replay repair action; replay stays feature-flag closed.
8. **No asynchronous outbox worker.** There are no external side effects in Phase 1. Core fixture projections are initialized transactionally.
9. **Local bearer authentication is minimal.** A static environment-provided token is sufficient for a loopback Phase 1 process; token lifecycle/port discovery packaging remains later product work.
10. **Distribution license remains provisional.** The runtime is marked AGPL-3.0-only following ADR-008, while legal/maintainer confirmation is still required before distribution.
