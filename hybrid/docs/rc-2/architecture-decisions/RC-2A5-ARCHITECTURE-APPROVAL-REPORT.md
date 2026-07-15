# RC-2A.5 Architecture Approval Report

Date: 2026-07-15
Committee role: independent architecture, event sourcing, database and migration governance review
Change boundary: documentation and read-only verification only

## 1. Executive Summary

RC-2A proved that supported legacy projects can contain authoritative current rows without complete revision-bound events. Live code still implements `at_revision` as a future-number check followed by a current-row read. The only honest architecture is therefore a Hybrid historical model with explicit limited-history boundaries, immutable revision manifests, a closed typed event catalog, transactional validity history and isolated replay.

All six blocking architecture decisions are approved or approved with implementation conditions. No core semantic question is deferred. RC-2B Batch 1 may implement only revision semantics and the immutable ledger/CAS foundation; event coverage remains Batch 2 and is a hard prerequisite to any public historical API.

## 2. Baseline

The decision baseline is [`RC-2A5-BASELINE.md`](./RC-2A5-BASELINE.md): `master@cefed3baffacea6fce715b856cc89bdfeaabc521`, equal to `origin/master`; Runtime `0.1.0`; OpenAPI `0.7.0`; public contract `story-runtime/v1`; DB migration 7; authority modes `legacy|runtime`; no reducer version. The worktree contained untracked documentation only and was not cleaned or counted as committed capability.

Live CI at this SHA is mixed: RC-1 Gate and authority-gates passed; phase9-cross-platform failed. RC-1 establishes current Runtime authority behavior, not history.

## 3. Reviewed Evidence

The committee reviewed the complete current copies of:

- [`RC-2A-AUDIT-REPORT.md`](../RC-2A-AUDIT-REPORT.md): limited history required; event coverage and replay gaps block implementation claims.
- [`RC-2A-BASELINE.md`](../RC-2A-BASELINE.md): versions, fixtures, RC-1/CI state and dirty-worktree isolation.
- [`AT-REVISION-AUDIT.md`](../AT-REVISION-AUDIT.md): revision 0/1/2 returned revision-3 current state; migration revision 0/1/6 returned revision-7 current state.
- [`EVENT-COVERAGE-MATRIX.md`](../EVENT-COVERAGE-MATRIX.md): direct imports, missing chapter-finalized/tombstone events, open operator append and unversioned reducers.
- [`HISTORICAL-DATA-MODEL-AUDIT.md`](../HISTORICAL-DATA-MODEL-AUDIT.md): current overwrite model, partial fact validity, no ledger/snapshot catalog and ambiguous projection ownership.
- [`HISTORICAL-QUERY-API-DRAFT.md`](../HISTORICAL-QUERY-API-DRAFT.md): uniform exact-revision contract, availability errors, bounded pagination and isolated replay direction.
- [`RC-2-IMPLEMENTATION-PLAN.md`](../RC-2-IMPLEMENTATION-PLAN.md): gated 12-batch dependency order.

Sampled live code corroborated the documents:

- `api.py:281-285`, `services.py:62-64`, `repository.py:122-130`: `at_revision` never reaches SQL.
- `migrations.py:26-118`: `projects.revision` is latest-only; events cascade with project; only facts have validity columns.
- `chapter_commits.py:351-376`: target replay clears current projections and writes current-revision checkpoints; summaries ignore target.
- `chapter_commits.py:393-426,726-771`: arbitrary operator events and aggregate-only reducer dispatch; unknown aggregates can be treated as facts selection.
- `chapter_commits.py:533`: recovery deletes events.
- `migration_jobs.py:861-885`: legacy import directly inserts projections and increments revision per imported event/chapter item.
- `migration_jobs.py:252-270`: authority cutover changes operational mode without a story transition.
- `fixtures/lighthouse-project.json`: populated current state at revision 7 without authentic revisions 0-6.

## 4. Decision 1 — Revision Semantics

**APPROVED.** [`ADR-RC2-001`](./ADR-RC2-001-PROJECT-REVISION-SEMANTICS.md) freezes per-project monotonic non-reusable revisions, native empty revision 0, one revision per atomic story command, idempotent retry neutrality and forward-only compensation/tombstone. Finalized revised chapter bodies increment once; proposals/reviews do not. Story-significant project metadata participates only through the closed command catalog.

No gaps are allowed after a managed lineage begins. A bootstrap lineage may start at R>0; pre-R integers are unavailable, not missing finalized revisions. Cutover audit is operational; a current-state bootstrap has one linked story transition, not a second increment for the mode flip.

## 5. Decision 2 — Limited History

**APPROVED.** [`ADR-RC2-002`](./ADR-RC2-002-LIMITED-HISTORY-BOUNDARY.md) classifies projects as native complete, verified import, bootstrap boundary, manifest-only, pruned or unavailable. Current-state migration creates one bootstrap event/manifest referencing a content-addressed state baseline. Pre-boundary state and structural diff return explicit unavailable errors.

A bootstrap legacy project does not acquire a fictional revision 0. It may remain limited forever. Later evidence is retained as provenance but cannot rewrite or splice finalized manifests; authoritative promotion requires a separately governed lineage.

## 6. Decision 3 — Hybrid Architecture

**APPROVED WITH CONDITIONS: Option C.** [`ADR-RC2-003`](./ADR-RC2-003-HYBRID-HISTORICAL-ARCHITECTURE.md) assigns revision integrity to manifests, transition semantics to events and referenced content bytes to immutable artifacts. Current projections serve latest; transactionally synchronized validity tables serve routine history; snapshots plus replay verify/recover; historical materialization is isolated.

Conditions are Batch 1 manifest/CAS atomicity, Batch 2 closed coverage/append-only enforcement and Batch 3 replay/history parity. HistoricalStateService is the sole history entry. Historical reads never substitute current projections.

## 7. Decision 4 — Event Coverage

**APPROVED.** [`ADR-RC2-004`](./ADR-RC2-004-EVENT-CATALOG-AND-COVERAGE.md) freezes the minimum typed catalog, complete envelope, deterministic IDs/hashes, contiguous ordinals, duplicate handling, fail-closed compatibility and append-only/retention behavior. Operator append cannot remain an arbitrary-event escape hatch.

Batch 2 coverage is a mandatory predecessor to historical storage completeness and public history. Migration inputs that cannot be deterministically adapted become provenance-only and require bootstrap.

## 8. Decision 5 — Replay Boundary

**APPROVED WITH CONDITIONS.** [`ADR-RC2-005`](./ADR-RC2-005-REPLAY-AND-REPAIR-BOUNDARY.md) separates historical materialization, verify and latest repair. Materialize/verify are isolated and read authority only. Repair requires latest target, explicit permission, complete compatible base, expected/result hash validation and an atomic swap guarded against concurrent latest advancement.

Cancellation, crash recovery, job states, quotas, progress and version/range fields are frozen. Target replay can never leave latest at an older revision.

## 9. Decision 6 — Batch Order

**APPROVED.** [`ADR-RC2-006`](./ADR-RC2-006-BATCH-ORDER-AND-GATES.md) freezes the 12 batches and entry/exit gates. Only within-batch documentation, fixtures, threat modeling and harness work may run in parallel. Semantic implementation remains serial. UI is Batch 9 because it must not invent semantics; API is Batch 7 because incomplete events cannot support an honest contract; migration is Batch 10 because boundaries/manifests must already be stable.

## 10. Data Ownership

[`RC-2-DATA-OWNERSHIP-MATRIX.md`](./RC-2-DATA-OWNERSHIP-MATRIX.md) assigns one owner per datum. Events are not co-authority with history/current tables; manifests do not own domain values; snapshots are never authority. Runtime alone owns SQLite, and all TypeScript/product surfaces use HTTP contracts.

## 11. Revision Manifest

[`REVISION-MANIFEST-SPEC.md`](./REVISION-MANIFEST-SPEC.md) freezes fields, canonical hashing, project-local range/ordinal continuity, zero-event prohibition, bootstrap representation, chapter/artifact/provenance links, command/idempotency uniqueness and one-transaction finalization. The sole zero-event manifest is native empty revision 0.

## 12. History Availability

[`HISTORY-AVAILABILITY-CONTRACT.md`](./HISTORY-AVAILABILITY-CONTRACT.md) freezes availability fields/enums and their placement in status/API/product surfaces. It distinguishes nonexistent revision, aggregate absence, pre-boundary unavailable history and retention-pruned payload. Signed cursors bind authorization, revision, filters and versions; every page reauthorizes.

## 13. Compatibility Policy

[`COMPATIBILITY-FAILURE-POLICY.md`](./COMPATIBILITY-FAILURE-POLICY.md) defines error code, HTTP status, retryability, operator/repair action, read/write effect and migration response for every required unknown, duplicate, range, hash, artifact and snapshot condition. Authority/history defaults fail closed. A bad snapshot falls back; bad authority never falls back to projections.

## 14. Legacy Compatibility

[`ADR-RC2-007`](./ADR-RC2-007-LEGACY-HISTORY-COMPATIBILITY.md) defaults legacy/current-only imports to bootstrap. Partial events may establish only a contiguous verified range or a full state boundary plus later complete transitions. Null revisions and arbitrary event types are never inferred; deterministic versioned adapters require external evidence. Manifests are immutable after cutover.

## 15. Rejected Alternatives

The committee explicitly rejects:

1. returning current state for every old revision;
2. fabricating revisions by import row count;
3. publishing historical API before event coverage;
4. validity history for entity while relationship or another domain returns latest;
5. target replay directly overwriting latest tables;
6. current projection as historical fallback;
7. silently ignoring unknown events;
8. arbitrary operator events bypassing the catalog;
9. snapshot as a second authority;
10. UI implementation before Runtime semantics/client contracts;
11. local Markdown as a history source;
12. deleting old authority events to repair replay;
13. migration audit as story revision ledger;
14. idempotency ledger as revision ledger.

No new evidence supports any rejected alternative. Ease of implementation is not an acceptance criterion.

## 16. Conditions of Approval

- “Approved with conditions” means the architecture is decided and the implementation must pass stated exit gates; it is not a deferred semantic decision.
- Batch 1 may add only revision allocation, immutable manifest/CAS mechanics and their tests/contracts. It may reference catalog/reducer version identifiers but cannot define or simulate domain payload history.
- Additive schema rollout must take verified Runtime snapshot/backup and produce a migration report. Once authoritative manifests exist, rollback disables new writes and requires a compatible reader; it never drops/reuses manifests or loses new events.
- Every later batch needs its prior exit evidence. No public history, TypeScript surface or UI is authorized by this report.
- Existing mixed CI remains a release concern; Batch 1 authorization does not declare repository CI green.

## 17. Batch 1 Entry Criteria

All criteria are satisfied at the architecture level:

- six core decisions approved; no deferred blocking item;
- revision, bootstrap, manifest, ownership and compatibility semantics frozen;
- event coverage explicitly assigned to Batch 2 before public history;
- Batch 1 does not depend on detailed domain payload schemas;
- rollback blocks incompatible old Runtime rather than discarding new authority;
- fabrication and current fallback are prohibited.

Batch 1 exit still requires implemented atomicity, concurrency, idempotency, no-gap/reuse behavior and revision-neutral operation tests. This report does not claim those tests exist.

## 18. Remaining Risks

- SQLite schema/trigger design must enforce append-only behavior without making governed project deletion or backup restore impossible.
- Large chapter/bootstrap artifacts need retention and encryption policy that preserves hash audit without retaining forbidden prose.
- Exact canonical JSON/Unicode/timestamp rules must be shared across Python/TypeScript fixtures before external manifest consumption.
- Reducer-version retention may require shipping old reducer implementations or deterministic adapters for the lifetime of retained history.
- Current mixed CI failures and dependency security finding are outside RC-2A.5 but remain release blockers.
- Existing untracked RC-2A evidence must be intentionally committed/reviewed before it can serve as default-branch governance evidence.

None is an unresolved architecture decision for Batch 1; each is an implementation/operational gate already assigned to a batch.

## 19. Final Authorization

```text
RC-2A.5 ARCHITECTURE APPROVED

Architecture:
HYBRID HISTORICAL MODEL

History policy:
LIMITED HISTORY WITH EXPLICIT BOOTSTRAP BOUNDARY

Replay policy:
ISOLATED VERIFY / LATEST-ONLY REPAIR

Event policy:
CLOSED VERSIONED EVENT CATALOG REQUIRED BEFORE PUBLIC HISTORY

Implementation authorization:
RC-2B BATCH 1 AUTHORIZED
```

Authorization stops at RC-2B Batch 1. No business code, schema, event model, API, tests or UI was modified or started by RC-2A.5.
