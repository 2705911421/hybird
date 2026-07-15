# RC-2 Data Ownership Matrix

Status: **Frozen / Accepted 2026-07-15**

“Authority” below names the one record class whose loss changes what the system can honestly claim. A manifest owns revision identity/integrity; an event owns a domain transition; an artifact owns referenced content bytes. Derived tables do not become co-authority because they are transactional.

| Data | Authority | Current projection | Historical read model | Cache/index | Backup/snapshot |
| --- | --- | --- | --- | --- | --- |
| project revision | finalized revision-manifest chain | `projects.revision` latest CAS pointer | manifest list/resolver | revision lookup index | DB backup; snapshot copies pointer only |
| revision manifest | immutable `project_revisions` manifest row/hash | latest manifest ID/hash pointer | same immutable manifests | command/commit/revision indexes | preserved in backup/snapshot, never replaced by it |
| chapter body | immutable content-addressed chapter artifact referenced by event/manifest | latest chapter artifact view | artifact versions selected by manifest/history | search/export body indexes | encrypted artifact/DB backup; snapshot may reference hash |
| chapter summary | typed summary transition/event payload or immutable referenced summary artifact | `chapter_summaries` latest | `chapter_summary_history` validity rows | retrieval/search index | derived snapshot segment |
| entities | typed event stream | `entities` | `entity_history` | entity/name lookup | derived snapshot segment |
| relationships | typed event stream | `relationships` | `relationship_history` | endpoint/type lookup | derived snapshot segment |
| facts | typed event stream | active fact projection | `fact_history` | subject/predicate lookup | derived snapshot segment |
| resources | typed resource event stream | resource projection (not convention-only facts) | `resource_history` | resource lookup | derived snapshot segment |
| timeline | typed event stream | `timeline` | `timeline_history` | narrative-order index | derived snapshot segment |
| threads | typed event stream | `narrative_threads` | `thread_history` | status/chapter index | derived snapshot segment |
| foreshadowing | typed foreshadow event stream | foreshadow projection | `foreshadow_history` | lifecycle/chapter index | derived snapshot segment |
| event stream | append-only canonical event envelope rows | event observability view only | event range read for replay/provenance | sequence/type/aggregate indexes | DB backup; snapshots reference offsets/hashes |
| diff index | none; rebuildable from manifests/events | none | optional change candidates | `revision_changes` derived index | optional derived snapshot segment |
| snapshots | none; non-authoritative accelerator | none | compatible replay base | snapshot catalog/checksum index | snapshot object plus independent DB backup |
| migration provenance | immutable migration provenance/source checksum ledger | current migration status view | boundary/provenance view | job/source lookup | DB backup; redacted export |

## Transactional write rule

For a normal story command, authority event(s), artifact references, validity history rows, current projections, manifest finalization and latest CAS pointer commit in one transaction. The manifest is finalized last logically within the transaction. Async outbox work may update only rebuildable caches/indexes.

## Recovery rule

- Delete/corrupt current projection: rebuild latest from compatible snapshot plus events, verify manifest state hash, atomically replace current.
- Delete/corrupt history model: rebuild in isolation from events/snapshots and atomically replace history tables.
- Corrupt snapshot: discard it and use an earlier compatible snapshot or full event replay.
- Missing/corrupt authority event, manifest or artifact: fail closed under the compatibility policy; never reverse-derive authority from a projection.

## Owner boundary

Story Runtime is the only owner allowed to read/write Runtime SQLite. TypeScript clients, Studio, CLI and TUI use Runtime HTTP and strict contracts. Latest projection and historical read model are implementation details behind separate Runtime services.
