# Event Coverage Matrix

## Verdict

**Event coverage is incomplete.** The existence of `story_events` and a passing projection-hash test does not make the Runtime fully event sourced. Supported migration/bootstrap paths write current projection rows directly; chapter finalization lacks a mandatory chapter-finalized authority event; deletion/tombstone/merge semantics are absent; event and reducer versions are not enforced.

## Event envelope actually stored

New commit/operator events can store `event_id`, `event_type`, `subject`, chapter, arbitrary JSON payload/evidence, confidence, commit ID, ordinal, aggregate type/ID, `schema_version`, timestamp and `applied_revision`.

Important limitations:

- payloads are not discriminated by event type;
- reducers branch on `aggregate_type`, not `event_type`;
- chapter events allow arbitrary event types;
- typed diff narrows event types, but operator append bypasses the authority-conflict validator after checking admin scope;
- no reducer version, causation ID, correlation ID, actor, provenance ID or tombstone contract is in the event envelope;
- `schema_version` and `applied_revision` are nullable for existing/bootstrap rows.

## Mutation coverage

`Partial` means at least one supported path changes authority without a complete replayable event.

| State-changing command | Event? / observed type | Payload/evidence | ID / aggregate / revision / ordinal | Reducer and projection | Undo / migration / provenance | Coverage |
| --- | --- | --- | --- | --- | --- | --- |
| finalized chapter commit | artifact-proposed events only; **no mandatory `chapter.finalized` event** | arbitrary proposed state events; body/summary live in artifact | deterministic SHA per commit+ordinal; all events share one resulting revision | aggregate reducers plus summary direct upsert | no compensating chapter event; summary rebuild reads artifacts | **Partial** |
| character create/update | `entity.upsert` on typed-diff path; arbitrary entity event on chapter path | full replacement entity fields; evidence optional | deterministic on stored paths; entity aggregate; one command revision | overwrites `entities`; appends only `{revision,event_id}` history marker | no delete/undo; migration directly inserts entity; provenance not linked | **Partial** |
| relationship update | `relationship.upsert` | source/target/type/attributes | deterministic; relationship aggregate; command revision | overwrites current relationship | no tombstone/undo; migration direct insert | **Partial** |
| fact mutation | `fact.upsert` or arbitrary fact event | predicate/value and optional CAS/governance fields | deterministic; fact aggregate; command revision | closes active row and inserts new fact | no delete event; migration direct insert | **Partial** |
| resource change | represented as fact, commonly `resource.*` predicate | value/delta fields are convention, not schema | fact aggregate; one command revision | fact reducer only | no dedicated resource identity/unit/tombstone; import direct | **Partial** |
| timeline event | `timeline.upsert` | sequence key/title/details | deterministic; timeline aggregate | overwrites current timeline row | no delete/undo; migration direct insert | **Partial** |
| thread create/advance | `thread.upsert` | status/details | deterministic; narrative-thread aggregate | overwrites current thread row | no transition-specific reducer validation; migration direct insert | **Partial** |
| thread resolve/defer | `thread.resolve`, `thread.defer` allowed in typed diff | same generic thread payload | deterministic; narrative-thread aggregate | same generic upsert reducer | reversal is another upsert, not explicit compensation | **Partial** |
| foreshadow create/reveal/resolve | no distinct aggregate; encoded as narrative thread | convention in status/details | narrative-thread identity only | generic thread reducer | no separate lifecycle/schema/provenance | **Partial / implicit** |
| world rule | fact event with `world.rule.*` predicate | typed validation may require `human_decision_id` on change | fact aggregate; command revision | fact reducer | operator append can bypass conflict validation; no explicit compensation | **Partial** |
| user manual edit | TypeScript Runtime path calls `commands/typed-diff`; local edit controller blocks Runtime-authority direct file edits | seven allowed upsert/resolve/defer types | deterministic via operator append | core reducers | no delete/merge vocabulary | **Covered only for allowed upserts** |
| direct operator append | yes, arbitrary event after admin-scope check | arbitrary event/payload/evidence | deterministic; increments project revision once | reducer selected by aggregate | no authority-conflict validation; provenance is reason only in request and not stored in event | **Unsafe escape hatch** |
| migration import | source `events` may create rows; entities/relationships/facts/timeline/threads/summaries/chapters are direct inserts | imported event evidence becomes `[]`; aggregate forced to `project` | imported ID; no commit/ordinal; revision increments only for imported event/chapter items | direct SQL, not reducers | separate provenance ledger has no event FK | **Not covered** |
| migration cutover | no story event | updates authority mode/phase/finalized time | no project revision increment | direct project update | audit in migration job only | workflow audit only; story revision semantics undefined |
| recovery action | no compensating authority event | recovery reason in transition/audit | may delete incomplete event rows; retry can reuse revision | rebuilds current projections | destructive event delete; no reducer compatibility manifest | **Not append-only** |
| rollback | no compensating event | migration job audit/snapshot | may delete whole legacy target or restore snapshot | direct DB restoration/deletion | provenance outside event stream | **Not covered** |
| delete/tombstone | no supported domain event/reducer | — | — | — | project deletion cascades events | **Absent** |
| merge/alias resolution | no Runtime domain event; migration resolves CIR/direct entity aliases | decision in migration job JSON | no event/revision binding | direct imported entity state | provenance not tied to resulting event | **Absent from authority event model** |
| review artifact validation | no story event; writes review audit | source revision/body hashes | does not increment project revision | no story reducer | source-revision audit retained | outside target story revision by proposed semantics |
| human review decision | no story event | decision JSON/finding decisions | does not increment project revision | changes commit eligibility, not story projection | auditable but mutable workflow view | outside target story revision by proposed semantics |
| revision-result validation | no story event; stores before/after body | full original/revised bodies and hashes | does not increment project revision or finalize body | marks findings stale directly | chapter diff audit only | not a story-state revision |
| outbox/index/snapshot export | no authority event required | side-effect payload | does not increment revision | cache/export worker | retry ledger present | correctly outside story revision |

## Reducer coverage

| Reducer | Accepted input in practice | Initial state | Ordering / duplicates / unknowns | Tombstone | Idempotency and hash | Compatibility / recovery |
| --- | --- | --- | --- | --- | --- | --- |
| entity | any event with aggregate `entity` | missing row | sequence order; logical duplicates append history; event type ignored | no | upsert; projection hash includes embedded history | no reducer version; recovery works only with complete events |
| relationship | aggregate `relationship` | missing row | sequence order; duplicate is last-write-wins; event type ignored | no | upsert; hash | no reducer version |
| fact/resource | aggregate `fact` or default | no active fact | sequence order; duplicates create additional validity rows; event type ignored | no | not idempotent without event de-dup before reducer; hash | validity is reconstructible only for covered events |
| timeline | aggregate `timeline` | missing row | sequence order; last-write-wins | no | upsert; hash | no reducer version |
| thread/foreshadow | aggregate `narrative_thread` | missing row | sequence order; event type ignored | no | upsert; hash | no reducer version |
| summary | **not event reducer** | empty table | bulk copies every finalized artifact; target revision is not applied | no | hash | depends on artifact table, not event stream |
| project status | **absent** | project row is separately updated | no event reconstruction | no | project not in projection hash | cannot rebuild project revision/phase from events |

## Dynamic replay audit

Temporary project `rc2a-project` had 15 events across revisions 1–3.

| Scenario | Observed result | Audit interpretation |
| --- | --- | --- |
| replay latest twice with different job keys | both `FINALIZED`, identical hash | deterministic for this valid stream |
| clear entity projection, replay latest | restored two entities | current event-covered entity recovery works |
| corrupt entity projection, replay latest | restored name and original hash | corruption can be repaired when stream is complete |
| replay non-dry-run to revision 2 | returned correct rev-2 entity/relation/facts | reducer can materialize a prefix |
| inspect after target replay | project stayed 3; checkpoints recorded 3 while tables held rev-2 state | **unsafe checkpoint/current-state inconsistency** |
| shuffle stored ordinals while preserving sequence | replay `FINALIZED` | ordinal inconsistency is not detected or used |
| insert logical duplicate with new event ID | replay `FINALIZED` | no semantic duplicate handling |
| insert unknown aggregate/event with `story-runtime/v999` | replay `FINALIZED` | unknown event and reducer/schema mismatch silently accepted |

The existing unit test `test_projection_replay_hash_is_deterministic` is valid but narrow: it proves a selected happy-path stream hashes deterministically in verify mode. It does not prove historical queries, complete event coverage, ordinal validation, duplicate handling, unknown-event policy or reducer compatibility.

## Required correction before historical claims

1. Define a closed, versioned event catalog with typed payloads and tombstones.
2. Require every story-state command, including migration/bootstrap, to produce a revision manifest and authority events or declare a history boundary.
3. Make reducers reject unknown event/schema/reducer versions and validate `(revision, ordinal)` continuity.
4. Separate current projection replay from historical materialization; target revision must never silently replace latest tables.
5. Add a mandatory finalized-chapter event referencing the immutable artifact and summary.
6. Protect authority events from update/delete except explicit administrative retention policy with audit.
