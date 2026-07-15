# RC-2A Audit Report

Audit date: 2026-07-15
Scope: true historical revisions, event reconstruction and time travel pre-implementation audit.
Change boundary: documentation only; no business code/schema/event/UI change and no RC-2B start.

## 1. Executive conclusion

```text
HISTORICAL DATA NOT RECOVERABLE — LIMITED HISTORY DESIGN REQUIRED
```

This conclusion is required because existing supported projects can contain current entities, relationships, facts, timeline, threads, summaries and chapters that were written directly rather than derived from revision-bound authority events. The committed lighthouse bootstrap proves the condition: project revision 7, two events with no `applied_revision`, zero chapter commits, yet a populated current state. No implementation can reconstruct honest revisions 0–6 from that data.

For native event-covered streams, current replay has useful deterministic-hash and corruption-repair behavior, but it is not safe as a historical query engine. Current `at_revision` is a confirmed latest-state pseudo-implementation. Event coverage must also be corrected before RC-2 can claim full event sourcing.

## 2. Fixed RC-2 semantics

### Revision

Revision is a per-project, monotonic, non-reusable logical version after one atomic authoritative story-state transition completes.

| Operation | Target revision effect |
| --- | --- |
| project initialized empty | revision 0 |
| finalized chapter | exactly +1 once; retries +0 |
| manual entity/fact/relationship/resource/timeline/thread/world mutation | +1 per atomic command |
| current-state-only migration | one bootstrap-boundary revision, not fabricated per-row history |
| verified historical migration | one or more only when authentic ordered source transition boundaries are evidenced |
| replay / projection repair | +0 |
| snapshot creation | +0 |
| review artifact / human decision | +0 story revision; remains bound to source revision |
| finalized revised body/state change | +1 |
| outbox/index/export | +0 |
| compensating rollback/tombstone | +1 new revision; never rewinds/reuses old revision |

### Historical query

`at_revision=R` returns project authority after R and before R+1. It may not return latest, a nearest projection, an event list, Markdown inference or a snapshot with undisclosed semantics. The response must identify effective revision, history boundary, event/reducer versions, state hash and provenance.

### Replay

Replay starts from immutable authority events, uses a versioned deterministic reducer, can rebuild from empty projections, does not mutate events/project revision, supports dry-run and target revision, rejects incompatible event/reducer schemas, and can repair projection corruption. Same stream plus reducer version must yield the same hash.

The current code meets only part of this definition.

## 3. Baseline and RC-1 relationship

The audited source is `master@cefed3baffacea6fce715b856cc89bdfeaabc521`, equal to `origin/master`. Runtime is `0.1.0`, InkOS `1.7.0`, OpenAPI `0.7.0`, contract `story-runtime/v1`, DB migration 7. Authority modes are `legacy|runtime`. No reducer/projection version exists.

The worktree started dirty only because of four untracked RC-1 documentation paths. They did not overlap implementation and were not counted as capability.

RC-1 current-authority gate is genuinely green for this SHA (run `29389871238`). Overall repository CI is not green because Phase 9 run `29389871215` has Studio build, supply-chain and Windows InkOS failures. Runtime jobs themselves passed. RC-1 proves current chapter authority and fail-closed behavior; it does not prove history.

## 4. Data-model findings

1. There is no project revision ledger or immutable revision manifest.
2. `projects.revision` stores only latest.
3. `entities`, `relationships`, `timeline`, `narrative_threads` and `chapter_summaries` overwrite current rows.
4. `facts` alone stores half-open validity candidates, but no historical public repository query uses them and import coverage is incomplete.
5. Resources are conventionally facts; foreshadowing is conventionally a narrative thread. Neither has a distinct schema/reducer.
6. `chapter_artifacts` retains finalized bodies but summary replay reads that authority table instead of events.
7. `projection_checkpoints` has hash/revision/offset but no reducer version.
8. Snapshots are external whole-DB ZIPs or non-authoritative outbox JSON, not a historical snapshot catalog consumed by replay.
9. Migration and fixture code directly writes projection tables.
10. Project deletion cascades events; recovery can delete commit events. Append-only is not enforced.

Full table-by-table answers are in `HISTORICAL-DATA-MODEL-AUDIT.md`.

## 5. Event coverage findings

Covered happy path:

- chapter-proposed events and typed diffs receive deterministic IDs;
- commit/operator commands bind multiple events to one incremented revision;
- entity, relationship, fact, timeline and thread reducers exist;
- current projections and checkpoints are updated atomically with normal commits;
- idempotent commit/operator retries do not increment again.

Blocking gaps:

- no mandatory chapter-finalized event covers artifact/summary/project transition;
- migration imports entities, relationships, facts, timeline, threads, summaries and chapters directly;
- no delete/tombstone or merge/alias event model;
- resources/foreshadowing have implicit, not versioned domain semantics;
- operator append accepts arbitrary event types and does not run typed-diff conflict validation;
- event payload is untyped by event type;
- unknown event/aggregate/schema/reducer versions do not fail closed;
- no reducer version or provenance link in the event envelope;
- project status is not event-reduced.

Therefore full event sourcing cannot be claimed. See `EVENT-COVERAGE-MATRIX.md`.

## 6. `at_revision` result

The route passes no revision to the service/repository. It reads current entity state, rejects only a future integer, and returns the latest project revision in the DTO.

Dynamic result after revisions 1/2/3 changed location/resource/relationship:

| Requested | Result |
| ---: | --- |
| 0 | HTTP 200, returned rev 3: vault / 2 / broken |
| 1 | HTTP 200, returned rev 3: vault / 2 / broken |
| 2 | HTTP 200, returned rev 3: vault / 2 / broken |
| 3 | HTTP 200, returned rev 3: vault / 2 / broken |
| 4 | HTTP 404 future revision |
| -1 | HTTP 422 validation |

Migration fixture requests 0/1/6/7 likewise returned the same rev-7 current state. There is no ledger to identify a nonexistent in-range revision. TypeScript has no entity historical method; Studio/CLI/TUI have no historical consumer. Full evidence is in `AT-REVISION-AUDIT.md`.

## 7. Reducer and replay audit

### Static behavior

- replay clears selected current projection tables and orders events by global `sequence`;
- `ordinal` is neither validated nor used for replay order;
- target revision filters nullable `applied_revision` but summaries ignore target revision and copy all finalized artifacts;
- `from_event_sequence > 0` still clears projections and has no required base snapshot;
- reducers select on aggregate type and ignore event type;
- unknown aggregate is mapped to the facts projection for selection, then silently does nothing in the reducer;
- non-verify target replay updates checkpoints using current project revision, not materialized target revision;
- verify-only rolls projection changes back but persists a replay job;
- event store/project revision are not changed by normal replay.

### Dynamic adversarial matrix

| Required scenario | Result |
| --- | --- |
| empty database to latest | unsupported as a self-contained operation; replay requires project/events already in the same DB |
| empty projections to latest | pass for covered event stream |
| replay to middle revision | reducer materialized correct rev-2 prefix, but unsafe latest-table/checkpoint inconsistency |
| same target twice | same hash, both finalized |
| delete projection then replay | restored covered entities |
| tamper projection then replay | restored expected name/hash |
| shuffled event ordinal | not detected; finalized |
| logical duplicate event | not detected; finalized |
| unknown event/aggregate | not detected; finalized |
| event schema/reducer mismatch | `story-runtime/v999` not detected; finalized |

The replay happy path is real. Arbitrary historical reconstruction and compatibility safety are not.

## 8. Architecture options

| Option | Read behavior | Write/recovery behavior | Fit to this repository | Decision |
| --- | --- | --- | --- | --- |
| A. validity tables | direct indexed SQL, predictable history reads | complex interval closure for every reducer; events still needed for recovery | facts provide a fragment, but other domains/current imports do not | insufficient alone |
| B. snapshot + event replay | clear semantics, cost proportional to events after snapshot | strongest event-source purity; reducer compatibility/snapshot lifecycle required | current event coverage and old projects are too incomplete; replay target is unsafe | future verification core, not sole first read path |
| C. hybrid | current projection for latest; versioned validity history for domain reads; snapshots+events verify/repair | moderate write amplification; strong recovery and bounded reads | best match for local SQLite, creative-context reads and current projection architecture | **recommended** |

Recommended design:

- immutable project revision manifests and complete authority event envelope;
- dedicated validity-history tables for all required domains, with one uniform `HistoricalStateService`;
- current projections remain optimized for latest;
- sparse compatible snapshots plus events independently verify/rebuild both history and latest;
- historical materialization is isolated and never overwrites current tables;
- existing projects declare `history_available_from_revision` and completeness.

The API must not expose that entities use validity SQL while another domain secretly returns latest or ad hoc replay. Internal implementation may differ, public revision semantics may not.

## 9. Performance evidence and estimates

Exact temporary corpus: 600 chapters, 10,000 events, 20,002 facts, 2,000 relationships, 500 threads, 320 entities, 1.08M deterministic CJK body characters.

| Operation | Current observed capability | Suggested design target (not an approved SLO) |
| --- | --- | --- |
| latest entity | p50 10.75 ms, p95 14.77 ms | preserve low tens of ms locally |
| revision 1 full state | unavailable; pseudo-route costs latest time but is wrong | indexed metadata/domain page <50 ms warm; bounded response |
| middle revision full state | unavailable | <100 ms warm for normal page; snapshot replay fallback bounded/async |
| latest-1 full state | unavailable | comparable to indexed history page, not full replay |
| direct fact count predicate at R | p95 10.82 ms (R1), 27.67 ms (R300), 12.26 ms (R599) | evidence for indexes only; not a complete product query |
| diff R1→R2 | unavailable | manifest/event accelerated; <100 ms for small delta, paged/async for large |
| full replay verify | 675.67 ms over 10,000 rows | retain sub-second local target if event validation/hashing allows; measure after correct events |
| middle replay | 277.88 ms but selected **0** events because bootstrap rows had null revision | invalid as performance proof |
| replay from snapshot | unavailable | choose cadence by measured tail; target hundreds, not 10k, events after snapshot |
| DB size | 21,151,744 bytes current fixture | plan 2–4x (roughly 45–90 MB) with full validity/events/indexes before snapshots; measure actual payloads |
| process RSS after fixture/replay | 83,177,472 bytes | stream pages/events; avoid materializing full state/diff in memory |
| initialization | 1,356 ms | migration/bootstrap only, not online query |

The current Phase 9 benchmark separately recorded 12,000-event replay at 768.743 ms and a 23,703,552-byte DB. These figures are consistent with this audit, but neither corpus contains revision-complete imported events, so they estimate throughput, not historical correctness.

Required indexes for the chosen design:

- events `(project_id, applied_revision, ordinal, sequence)` and manifest event ranges;
- revision manifests `(project_id, revision)` plus command/commit uniqueness;
- each history table `(project_id, aggregate_id, valid_from_revision, valid_to_revision)` and revision/change scan indexes;
- snapshot `(project_id, reducer_version, snapshot_revision DESC)`;
- diff/change index `(project_id, revision, aggregate_type, aggregate_id)` if measurement justifies it.

No existing SLO is changed by this report.

## 10. Migration and compatibility

Existing projects fall into four classes:

1. native complete after a new event-coverage gate;
2. verified imported history from an evidenced source revision;
3. current-state bootstrap at boundary R, with history before R unavailable;
4. manifest-only/pruned payload under an explicit retention policy.

Current legacy import is class 3 unless source events and transition boundaries are independently verified. It directly inserts current state, increments revision per imported event/chapter rather than per evidenced atomic authority transition, and does not emit complete projection events. Old payloads can lack aggregate, commit, ordinal, schema and applied revision.

Required policy:

- never copy current state into earlier revisions;
- synthesize at most an explicit bootstrap event/manifest saying “state became authoritative at boundary,” not invented prior changes;
- publish `history_available_from_revision` and return `HISTORY_UNAVAILABLE` earlier;
- link migration provenance to the bootstrap/verified manifests without exposing local paths;
- preserve source checksums/mapping versions and make re-import idempotent.

## 11. Security and privacy

Current positive controls include loopback/bearer assumptions, strict request models, request body limit, event payload preview truncation/redaction and migration API path fingerprinting.

RC-2 risks requiring explicit controls:

- old snapshots/events may retain deleted prose, role names or sensitive user edits;
- current authorization cannot be assumed to grant historical access forever;
- unbounded state/diff/replay can cause memory/CPU/SQLite denial of service;
- target-revision replay must not be a synchronous expensive GET side effect;
- project/revision-specific error differences can enable enumeration to a bearer holder;
- snapshot tokens can become capability leaks if not bound to subject/project/expiry;
- migration job/CIR/discovery/checksum metadata may contain filenames or source paths even though the top-level DTO omits raw `source_path`;
- historical caches can outlive permission or deletion policy changes.

Required controls: per-project reauthorization, separate history/replay/repair scopes, uniform unauthorized responses, signed bound cursors, page/byte/revision-span limits, per-project job concurrency, cancellation/timeouts, encrypted sensitive snapshots, retention/tombstone policy and path/prose redaction.

## 12. Deliverables and next gate

Generated:

- `RC-2A-BASELINE.md`
- `HISTORICAL-DATA-MODEL-AUDIT.md`
- `EVENT-COVERAGE-MATRIX.md`
- `AT-REVISION-AUDIT.md`
- `HISTORICAL-QUERY-API-DRAFT.md`
- `RC-2-IMPLEMENTATION-PLAN.md`
- this report

RC-2B must not start automatically. Approval should first accept:

1. the per-project story-revision semantics;
2. limited-history/bootstrap-boundary policy;
3. Hybrid architecture;
4. event coverage correction as a prerequisite;
5. isolated replay versus current projection repair boundary;
6. the 12-batch implementation order.

Until those are accepted and implemented, historical queries must be described as unavailable, not approximated by current state.
