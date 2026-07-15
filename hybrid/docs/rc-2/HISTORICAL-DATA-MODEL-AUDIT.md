# Historical Data Model Audit

## Executive finding

The schema is a transactional current-state system with an event-assisted projection layer, not a complete historical model. `story_events` is useful but incomplete; `facts` is the only story-state table with validity columns; all other core projections overwrite current rows. There is no revision ledger, reducer-version registry, historical snapshot catalog or project-wide historical manifest.

A second structural problem is ownership ambiguity: chapter commit and typed-diff paths derive projections from events, while fixture and legacy migration paths write those same projection tables directly. A table cannot be treated as safely deletable projection data while supported workflows also use it as the only retained representation of imported authority.

## Required-domain matrix

Notation: `A` authority, `P` projection, `C` cache/index, `U` operational/audit. `—` means the concept or field does not exist.

| Domain / table | Class | Primary key | Revision | Valid from / to | Event and commit linkage | Project isolation | Schema/reducer version | Historical support | Current-only? | Rebuild after delete? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `projects` | A | `project_id` | current `revision` only | — / — | none | row is project root | `schema_version`; no reducer version | no revision rows | yes | no; events cascade-delete with project |
| revisions | **absent** | — | — | — | — | — | — | no ledger or manifest | — | no |
| `chapter_commits` | A + workflow audit | `commit_id`; unique finalized chapter | expected/resulting | — / — | commit is parent for artifact/events/transitions/outbox | FK to project | `schema_version` | preserves finalized commit boundary | append-like except recovery/state updates | not solely from events |
| `commit_transitions` | U/audit | autoincrement `transition_id` | expected/resulting | timestamp only | FK `commit_id` | `project_id` copied, not FK | `schema_version` | workflow history, not story state | no | no |
| `chapter_artifacts` | A immutable payload | `commit_id` | only through commit join | — / — | FK commit; stores original `events_json` | project FK | `schema_version` | finalized chapter versions only; one finalized chapter enforced | effectively one current finalized artifact per chapter | not from event payloads |
| `story_events` | intended A event log | autoincrement `sequence`; unique `(project,event_id)` | `applied_revision` nullable | — / — | optional `commit_id`, `ordinal`, aggregate IDs | project FK | nullable `schema_version`; no event-envelope/reducer version | partial, only rows actually emitted | append path mostly; recovery/project deletion can delete | source for covered projections only |
| `entities` | P, but direct-import/fixture writes blur ownership | `(project_id,entity_id)` | embedded `history_json` only | — / — | no FK to event/commit | project FK | none | no; history lacks state payload | yes | only for event-covered entities |
| `relationships` | P with direct-import exception | `(project_id,relationship_id)` | — | — / — | none | project FK | none | no | yes | only for event-covered relationships |
| `facts` | P/history fragment with direct-import exception | `(project_id,fact_id)` | `valid_from_revision` | yes / nullable `valid_to_revision` | fact IDs from events only on reducer path; no FK | project FK | none | partial bitemporal-like transaction validity only | no, but coverage incomplete | only event-covered facts; replay deletes/rebuilds selected range |
| resources | **no table**; encoded as facts/payload fields | fact key | fact validity only | fact semantics | event only if emitted as `fact` | fact project FK | none | partial at best | depends on fact path | no independent reducer |
| `timeline` | P with direct-import exception | `(project_id,timeline_id)` | — | — / — | nullable `event_id`, not FK | project FK | none | no | yes | only event-covered rows |
| `narrative_threads` | P with direct-import exception | `(project_id,thread_id)` | — | — / — | none | project FK | none | no | yes | only event-covered rows |
| foreshadowing | **no table**; folded into narrative threads | thread key | — | — / — | narrative-thread event if emitted | thread project FK | none | no separate semantics | yes | no separate reducer |
| `chapter_summaries` | P, also direct fixture/import output | `(project_id,chapter_number)` | — | — / — | derived from artifact/commit, not event | project FK | none | no | yes | from finalized artifacts, not events alone |
| `projection_checkpoints` | U/P metadata | `(project_id,projection_name)` | checkpoint + `applied_revision` | — / — | `event_offset`; no event FK | project FK | **no projection/reducer version** | latest checkpoint only | yes | recreated by replay, but version compatibility unknown |
| snapshots | **no DB catalog/table** | — | manifest field in external files | — / — | no event linkage | optional project ID in file manifest | file format v1 + DB schema | whole-DB backup only, not historical query snapshot chain | point-in-time files outside DB | restore only as separate DB |
| `replay_jobs` | U/audit | `replay_job_id` | optional `target_revision` | — / — | sequence range and projection names | project FK | no reducer version | job history only | result rows | not a projection |
| `migration_jobs` | U + staged import authority | `job_id` | estimated/import result only in JSON | — / — | no event/commit linkage | `target_project_id` is not an FK | `mapping_version`, `cir_version` | source/workflow history, not project history | staged current record | no |
| `migration_import_ledger` | U/provenance | `(job_id,cir_item_id)` | — | imported timestamp | links job/item, not Runtime event | through job only | payload SHA, item kind | import audit only | append per imported item | no |
| `migration_source_provenance` | U/provenance | composite job/item/path/hash | — | — / — | links source item, not Runtime event | through job only | source SHA/kind | source audit only | append per source | no |

## Other relevant tables

| Table | Role | Historical implication |
| --- | --- | --- |
| `idempotency_ledger` | command result ledger | not a revision ledger; operation keys can prove retries but not reconstruct state |
| `outbox` | rebuildable side-effect queue | index/export/snapshot updates do not change project revision; mutable status is operational |
| `retrieval_documents` + FTS tables | cache/search index | current text only; should never answer historical authority queries |
| `review_artifacts`, `review_findings` | version-bound review audit | source revision retained, but findings are mutated to `stale`; no event stream |
| `human_review_decisions`, `review_finding_decisions` | review authority/audit | source revision retained; no project revision increment and no story event |
| `revision_results` | chapter revision proposal/result audit | despite its name, does not create a project revision or replace the finalized chapter |
| `review_operations` | idempotency/audit | not state history |
| `recovery_jobs`, `recovery_audit` | operational audit | recovery history only; not enough to rebuild story state |
| `runtime_incidents` | operational audit | mutable resolution status, unrelated to historical story state |
| `schema_migrations` | DB migration ledger | schema history, not project revision history |

## Validity semantics observed

The fact reducer closes an old row by setting `valid_to_revision=R` and inserts the new row with `valid_from_revision=R`. Therefore the only coherent query interval is:

```sql
valid_from_revision <= :R
AND (valid_to_revision IS NULL OR :R < valid_to_revision)
```

No public repository method currently executes this historical predicate. Current context reads explicitly require `valid_to_revision IS NULL`. Entities, relationships, timeline, threads and summaries have no equivalent interval.

## Deletion and append-only findings

- Deleting a project cascades into `story_events`; the event store is not protected as append-only at schema level.
- Commit recovery explicitly deletes events for a recovering commit before rebuilding projections.
- Migration rollback can delete an imported project and its events.
- There are no tombstone event types or reducer branches.
- Replay clears projection tables. This is acceptable only if the selected event stream is complete; migration and fixture paths make that assumption false.

## Historical recoverability by domain

| Domain | Native Runtime commits/typed diffs | Legacy migration/bootstrap | Honest current claim |
| --- | --- | --- | --- |
| facts/resources | potentially reconstructible when every mutation emitted an event | current values may be inserted without events | partial history only |
| entities | latest reconstructible for event-covered IDs; history payload not reconstructible from `history_json` alone | current rows direct-inserted | no general history |
| relationships | latest reconstructible for event-covered IDs | direct-inserted | no general history |
| timeline | latest reconstructible for event-covered IDs | direct-inserted | no general history |
| threads/foreshadowing | latest reconstructible for event-covered IDs | direct-inserted | no general history |
| chapter summaries | rebuildable from finalized artifacts, not from events alone | direct-inserted summaries/chapters | no event-only replay |
| chapter bodies | retained in finalized artifacts | imported artifact may exist | versions before retained artifacts are unavailable |

## Required schema direction for RC-2B planning

Before implementation, introduce an explicit project revision ledger and an event envelope that binds every authoritative transition to exactly one project revision, event schema, reducer version and provenance manifest. Do not add historical query SQL to current overwrite tables and call it complete. Existing current-only imports require a declared `history_available_from_revision` boundary.
