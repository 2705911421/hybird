# RC-2 Implementation Plan

This is a gated plan, not authorization to begin RC-2B. Batches are sequential unless a batch explicitly declares a safe parallel documentation/client task. No UI time travel begins before Runtime historical semantics, storage and query contracts are accepted.

## Target revision semantics

- Revision is **per project**, monotonic, never reused.
- Revision 0 is the empty initialized project state.
- One atomic authoritative story-state command produces exactly one new revision and one immutable revision manifest, regardless of event count.
- One finalized chapter increments exactly once. Idempotent retries do not increment.
- Manual fact/entity/relationship/resource/timeline/thread/world-rule edits increment once per atomic command.
- Current-state-only migration produces one honest bootstrap-boundary revision. Verified source history may produce multiple revisions only when original atomic order/boundaries are evidenced; never one fake revision per imported row.
- Replay, snapshot creation, index/outbox processing and projection repair do not increment revision.
- Review artifacts and review decisions bind to a story revision but do not increment story revision unless a separate future product decision expands revision semantics. A finalized revised chapter/body mutation does increment once.
- Recovery of projection corruption does not increment. A compensating story rollback or tombstone is a new command and revision; old revisions are never rewound.

## Batch 1 — Revision semantics

**Modify:** formal ADR/contract, revision allocator, immutable `project_revisions` manifest, project compare-and-swap transaction.
**Do not modify:** domain reducers, public historical reads, UI.
**Schema:** additive revision table with `(project_id,revision)` PK, previous hash, command/commit IDs, event range/count, manifest hash, event/reducer versions, provenance and timestamps; uniqueness for command identity.
**Tests:** concurrency, idempotent retry, revision 0, no gaps/reuse, one chapter/one revision, each excluded operation remains revision-neutral.
**Rollback:** feature flag and additive table; disable new writes before rollback. Never drop manifests once authoritative writes use them.
**Complete when:** every authority transaction has one manifest and the semantic decision table is contract-tested.

## Batch 2 — Event coverage corrections

**Modify:** closed event catalog, typed payload validators, mandatory chapter-finalized/artifact-reference event, tombstone and compensation vocabulary, migration/bootstrap event path, operator append restrictions.
**Do not modify:** historical read API or UI.
**Schema:** event envelope v1 fields for revision, ordinal, event/payload schema, reducer family/version, causation/correlation, actor class and provenance reference; append-only guards.
**Tests:** every command in `EVENT-COVERAGE-MATRIX.md`, forbidden direct projection writes, ordinal continuity, duplicates, unknown types, evidence/provenance.
**Rollback:** keep old reader adapters during a compatibility window; stop new envelope writes before binary rollback.
**Complete when:** mutation-to-event coverage is 100% or explicitly classified outside story revision; no authority mutation reaches a projection-only path.

## Batch 3 — Historical storage and reducers

**Modify:** deterministic versioned reducers; validity history for entities, relationships, facts/resources, timeline, threads/foreshadowing and summaries; isolated historical read model; sparse snapshot catalog.
**Do not modify:** product client/surfaces.
**Schema:** `*_history` tables with half-open revision intervals and source event; reducer registry; snapshot catalog/checkpoints with state hash and compatibility range. Keep current projection separate.
**Tests:** empty-state replay, each intermediate revision, tombstones, same-stream/same-version hash, unknown/mismatch fail closed, corruption recovery, cross-project isolation.
**Rollback:** write both current and history behind a flag until parity; retain events/manifests; history tables can be ignored but not silently dropped after serving clients.
**Complete when:** all required domains reconstruct R identically from empty and from a compatible snapshot.

## Batch 4 — Historical query service

**Modify:** one revision resolver and `HistoricalStateService`, tokenized stable pagination, history-boundary/error model.
**Do not modify:** diff, replay jobs, TypeScript or UI.
**Schema:** normally none beyond batch 3; optional bounded read-cache keyed by project/revision/reducer/auth scope.
**Tests:** 0/1/middle/latest-1/latest/future/missing/pruned/boundary, pagination under concurrent new commits, all-domain semantic parity, authorization.
**Rollback:** endpoint feature flag; latest service remains independent.
**Complete when:** no historical route can reach current repositories directly and pseudo-implementation regression tests fail on latest substitution.

## Batch 5 — Diff

**Modify:** manifest/event accelerated diff plus state-hash verification; bounded value expansion.
**Do not modify:** replay repair or UI visualization.
**Schema:** optional change index keyed by project/revision/aggregate; rebuildable from manifests/events.
**Tests:** create/update/tombstone/restore, reverse range rejection, migration boundary, large diff pagination/limits, deterministic ordering.
**Rollback:** disable endpoint/drop rebuildable change index only.
**Complete when:** diff equals independent state comparison for randomized fixtures and respects response limits.

## Batch 6 — Replay jobs

**Modify:** asynchronous isolated replay queue, verify/repair modes, progress/cancellation, atomic latest swap only.
**Do not modify:** event store/project revision; no target-revision replacement of latest tables.
**Schema:** replay job version, target, event/snapshot ranges, schema/reducer versions, hashes, progress, bounded diagnostics and audit.
**Tests:** all nine adversarial replay cases, crash/restart, cancellation, concurrent project jobs, cost quota, no event/revision mutation.
**Rollback:** stop workers and leave auditable jobs; current projection remains untouched unless a completed verified atomic swap occurred.
**Complete when:** replay can repair latest corruption and verify any available R without semantic cross-contamination.

## Batch 7 — Runtime API

**Modify:** endpoints in `HISTORICAL-QUERY-API-DRAFT.md`, strict request/response schemas, authorization/cost controls, OpenAPI.
**Do not modify:** TypeScript surfaces.
**Schema:** contract artifacts only unless job/token persistence is required.
**Tests:** OpenAPI conformance, error taxonomy, response bytes, pagination tokens, permission matrix, malicious high-cost requests.
**Rollback:** route feature flag and compatible error response; never fall back to latest.
**Complete when:** contract tests prove uniform revision semantics across every endpoint.

## Batch 8 — TypeScript client

**Modify:** strict Zod schemas/client methods for revisions/state/domains/diff/replay jobs; compatibility handshake.
**Do not modify:** Studio/CLI/TUI presentation.
**Schema:** generated or hand-audited v2 DTOs; no `unknown` passthrough for authority fields.
**Tests:** Python/TS shared fixtures, malformed/unknown versions, token binding, all error mappings, no SQLite/filesystem access.
**Rollback:** client capability negotiation; old clients do not see historical feature.
**Complete when:** every API response is validated and no consumer can silently coerce missing history to latest.

## Batch 9 — Studio / CLI / TUI

**Modify:** revision selector, state inspection, diff and job status; explicit unavailable/pruned/boundary UX.
**Do not modify:** Runtime semantics or storage; no local Markdown fallback.
**Schema:** no DB schema; view models only.
**Tests:** browser/TUI black-box for 0/middle/latest, deleted items, permission loss, Runtime failure/version mismatch, large pagination and job cancellation.
**Rollback:** UI feature flag removes controls; current reads remain Runtime-authoritative.
**Complete when:** all three surfaces display the same effective revision/hash and never present latest as historical.

## Batch 10 — Migration and compatibility

**Modify:** classify existing projects, create bootstrap boundaries, optional verified historical import adapters, event/manifests for future migration, provenance.
**Do not modify:** source files; never synthesize unknown intermediate states.
**Schema:** `history_availability`/boundary metadata and mapping adapter versions; provenance links from manifests/events.
**Tests:** current-only fixture, partial events, null applied revisions, old payload versions, re-import idempotency, rollback, path redaction, honest boundary errors.
**Rollback:** restore verified pre-import snapshot before cutover; imported manifests remain audit records if cutover occurred.
**Complete when:** every project is labeled complete/verified-from-R/bootstrap-from-R/pruned, and no pre-boundary query returns fabricated state.

## Batch 11 — Performance

**Modify:** indexes, snapshot cadence, cache policy, streaming/bounds and query plans based on measurement.
**Do not modify:** semantic definitions or SLOs without separate approval.
**Schema:** likely `(project_id,applied_revision,ordinal/sequence)`, history interval/identity indexes, snapshot lookup and diff indexes.
**Tests:** exact 600/10k/20k/2k/500 scale, skewed hot aggregates, cold/warm cache, revision 1/middle/latest-1, full/snapshot replay, DB growth/RSS, cancellation.
**Rollback:** indexes/caches are additive/rebuildable; snapshot cadence can be reduced without changing results.
**Complete when:** measured report and query plans exist for all requested operations with no semantic shortcuts.

## Batch 12 — CI gates

**Modify:** dedicated RC-2 workflow and release dependency, cross-platform deterministic history/replay/security/performance gates.
**Do not modify:** tests to tolerate pseudo-history, unknown reducers or latest fallback.
**Schema:** test fixtures/manifests only.
**Tests:** full matrices from batches 1–11, migration boundaries, fuzz/property replay, corruption drills, TS shared contracts, Studio/CLI/TUI black-box.
**Rollback:** release stays blocked if the gate is disabled or missing; workflow rollback cannot declare RC-2 complete.
**Complete when:** a clean default-branch run passes every blocking job and branch/release policy consumes the aggregate gate.

## Cross-batch stop conditions

Stop and return to design if any batch would:

- require fabricating pre-boundary history;
- let domain endpoints use different hidden revision semantics;
- update/delete authority events during normal replay;
- make target-revision replay overwrite latest projections;
- accept unknown event/reducer versions;
- allow InkOS/Studio/CLI/TUI to open Runtime SQLite or local prose as authority.
