# Phase 8 removal audit

Date: 2026-07-13  
Status: **completed; actual-project gate passed**

The deletion gate is supported by `phase-7-actual-project-acceptance.md`. Items marked `unknown` below were not deleted.

## Inventory and disposition

| # | Surface | Disposition | Phase 8 result |
|---|---|---|---|
| 1 | InkOS Writer Truth writes, legacy draft/revise/repair/resync/import and interaction Truth tools | `remove` | Writer save methods, legacy persistence implementation, file-edit controllers and long-form mutator registrations removed. Retired public methods fail closed with migration/Runtime guidance. |
| 2 | Automatic Markdown bootstrap and Markdown-to-JSON rewrite | `remove`; source parsing `retain as importer` | Normal load, compose, write and memory retrieval no longer invoke bootstrap. `state-bootstrap.ts` was deleted; the explicit migration service retains only the source parsing and provenance it needs. |
| 3 | JSON StateManager story writes | `remove` for authority; product metadata `retain as projection` | Long-form commit no longer selects the JSON/file persistence chain. Book/session configuration and read-only legacy metadata remain application-owned. |
| 4 | InkOS `story/memory.db` long-form writes | `remove` | Runner and retrieval paths no longer instantiate `MemoryDB`; public export removed. The implementation remains internal only for Interactive Film, recorded in ADR-011. |
| 5 | Studio Truth/chapter/raw state writes | `remove` / `deprecate` tombstone | Truth PUT, chapter PUT, repair, resync, rewrite, approve/reject and legacy imports return 410 guidance. A typed-diff proxy is the editable fact/world/relation/thread path. No raw Runtime DB route exists. |
| 6 | Agent file and authority tools | `remove` | Truth, patch, replace, rename, import, generic edit and generic write constructors were removed from code and registry. Read denies DB and migration snapshot paths in code. |
| 7 | Legacy chapter persistence | `remove` | `chapter-persistence.ts`, `LegacyChapterPersistence`, legacy pipeline tests and direct Writer persistence were deleted. `StoryRuntimeChapterPersistence` remains the sole long-form adapter. |
| 8 | webnovel Dashboard and Claude plugin runtime | `remove` from product; history `retain as importer` | They are not imported or packaged by InkOS/Runtime. The upstream source tree, license and mapping provenance remain available for importer/reference history. CI prevents product imports. |
| 9 | JSON-first event/commit authority and SQLite mirror dual-write | `remove` | No product import or call path remains. Runtime transaction/event/projection tables are the single authority chain. |
| 10 | Direct SQLite | Runtime `retain`; importer `retain as importer`; Play/Film `retain for non-long-form` | Architecture gate rejects Runtime storage access from TypeScript/Studio. Runtime and migration code own authorized SQLite. Play/Film exceptions have separate roots and ADR ownership. |
| 11 | Hidden fallback: legacy, shadow, Runtime-unavailable fallback, Markdown memory fallback | `remove` / legacy config `deprecate` read-only | New default is `story-runtime`, fallback false. Context selection rejects legacy/shadow and fails closed. Config setter rejects retired modes; migration script backs up and rewrites old config. |
| 12 | Play, Short Fiction, Interactive Film, Translation | `retain for non-long-form` | Separate stores/output roots, tool capabilities and backup/export behavior are fixed by ADR-011 and covered by regression tests. |
| 13 | Legacy parser, provenance, snapshots, source history | `retain as importer` | Phase 7 CIR mapping, conflict decisions, checksums, source parsers, verified snapshot and rollback remain. No importer auto-runs. |
| 14 | Markdown/TXT/EPUB, readable snapshot, migration report, Play/Short/Film exports | `retain as projection` or `retain for non-long-form` | Exports remain non-authoritative. Raw Runtime SQLite download remains absent. |

## Unknown no-delete list

| Item | Mark | Reason |
|---|---|---|
| `inputGovernanceMode=legacy` | `unknown` | Prompt assembly compatibility is not proven to be story authority. It was not deleted. |
| legacy session transcript migration | `unknown` | Conversation history ownership is separate from story authority. It was not deleted. |
| mixed StateManager book/session configuration helpers | `unknown` | Product metadata callers remain. Only long-form authority callers were removed. |
| existing non-authority UI component exports reported by Knip | `unknown` | Dynamic UI use and bundler reachability require a separate targeted cleanup; none were deleted here. |

## Reachability findings

- `PUT /api/v1/project/artifacts/:file` is limited to non-long-form generated roots (`dramas`, `storyboards`, `interactive-films`, `shorts`, `covers`); it cannot reach `books`, Runtime data or migration snapshots.
- `MemoryDB` has one non-test constructor caller: Interactive Film authoring under `interactive-films/<id>`.
- Studio has no SQLite API import and no raw database download route.
- The upstream webnovel Dashboard/plugin tree has no product import or package dependency.
- Markdown bootstrap and its parser module have been deleted. Markdown parsing exists only inside explicit migration/export surfaces and cannot auto-trigger during normal operation.

No `unknown` item was used as a deletion target.
