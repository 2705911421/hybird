# Removed legacy paths

Date: 2026-07-13

| Removed or disabled path | Replacement |
|---|---|
| `pipeline/chapter-persistence.ts` | `StoryRuntimeChapterPersistence` |
| `LegacyChapterPersistence` | Runtime prepare/validate/commit |
| Writer `saveChapter` / `saveNewTruthFiles` | typed proposal and Runtime transaction |
| legacy draft/revise/repair/resync/import implementation | Runtime command or migration wizard |
| Runner long-form `MemoryDB` rebuild/sync | Runtime context query and projections |
| automatic Markdown bootstrap/rewrite | explicit migration importer only |
| `state/state-bootstrap.ts` | migration service source parser and provenance only |
| `agent/chapter-import-source.ts` | explicit Runtime migration wizard |
| `LegacyTruthContextProvider`, shadow diff and fallback | fail-closed Runtime provider |
| Agent Truth/patch/replace/rename/import/edit/write tools | read, proposal, review artifact and Runtime command request |
| long-form Agent prompt claims for direct Truth/chapter tools | typed-diff and chapter-revision requests |
| interaction Truth/chapter/control-file edit transactions | typed proposal / Runtime command |
| Studio direct Truth/chapter/state/review/import writes | HTTP 410 guidance or typed-diff/migration Runtime API |
| Studio foundation edit control and `books/**` chat edit bypass | typed Runtime command path |
| new legacy-authority book mode | Runtime-only book initialization |
| CLI `memory.db` authority/fallback warnings | Runtime doctor/status diagnostics |
| webnovel Dashboard/Claude hooks as product runtime | Studio Runtime panel; upstream kept as provenance only |

Compatibility readers and route tombstones do not write authority. They exist only to keep unmigrated projects understandable and migratable.
