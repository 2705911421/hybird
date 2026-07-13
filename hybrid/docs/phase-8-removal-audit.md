# Phase 8 removal audit

Date: 2026-07-13  
Status: **deletion blocked**

## Gate decision

Phase 8 deletion is not authorized yet. `phase-7-test-report.md` says the executed migration coverage used deterministic generated fixtures and explicitly says that no real source project was used. No checked-in report, migration job artifact, checksum manifest, cutover record, or rollback record proves an actual legacy project completed:

`read-only discovery -> scan -> decisions -> dry-run -> verified snapshot -> import -> verify -> explicit cutover -> rollback/restore exercise`.

The repository also contains no non-fixture InkOS book or webnovel project suitable for performing that acceptance run. `inkos/test-project` and generated Phase 7 fixtures are test inputs, not an actual user project. Therefore this audit performs inventory and classification only. It does not delete, disable, redirect, or migrate any production path.

Deletion may start only after a real-project evidence bundle records source type/path label, pre-migration checksums, conflict decisions, dry-run report, snapshot checksum, import ledger, 100% chapter-body coverage, replay/projection hash equality, explicit cutover, post-cutover doctor, export result, and a rollback/restore exercise. Private source paths and manuscript content must not be committed; hashes and redacted identifiers are sufficient.

## Classification legend

| Mark | Meaning |
|---|---|
| `remove` | Delete from final long-form product after the gate passes. |
| `retain as projection` | Keep only as rebuildable/read-only output of Runtime authority. |
| `retain as importer` | Keep only behind the explicit Phase 7 migration command; never auto-run. |
| `retain for non-long-form` | Keep behind a separately owned Play/Short/Film boundary. |
| `deprecate` | Keep temporarily with a visible warning and a dated removal contract. |
| `unknown` | Ownership/callers are not proven; deletion is forbidden until resolved. |

## 1. Old Truth write entry points

| Code/path | Current behavior | Classification | Required Phase 8 action |
|---|---|---|---|
| `inkos/packages/core/src/agents/writer.ts` (`saveNewTruthFiles`) | Writes Markdown Truth after chapter generation. | `remove` | Long-form pipeline must emit typed proposals; Runtime performs validated mutations. |
| `inkos/packages/core/src/pipeline/runner.ts` (`writeDraft`, `reviseDraft`, `repairChapterState`, `resyncChapterArtifacts`, `importChapters`) | Calls chapter/Truth/state/index/snapshot writers directly on legacy books. | `remove` | Unmigrated books become read-only; import moves to the explicit migration service. |
| `inkos/packages/core/src/pipeline/chapter-persistence.ts` | Runs chapter -> Truth -> index -> snapshot -> memory-history file persistence. | `remove` | Remove as a long-form commit implementation after all callers use Runtime. |
| `inkos/packages/core/src/pipeline/chapter-persistence-port.ts` (`LegacyChapterPersistence`) | Selects the old multi-file authority chain. | `remove` | Keep only `StoryRuntimeChapterPersistence` for long-form. |
| `inkos/packages/core/src/state/runtime-state-store.ts` (`saveRuntimeStateSnapshot`) | Writes `story/state/*.json`. | `retain as projection` | Replace calls with a Runtime export/projection consumer; it must not accept authority edits. |
| `inkos/packages/core/src/state/manager.ts` | Writes book config, chapter index, snapshots and legacy state files. | `unknown` | Split product metadata from story authority before deletion; chapter/Truth parts are removable, book/session metadata may remain application-owned. |
| `inkos/packages/core/src/interaction/project-tools.ts` (`writeTruthFile`) | Deterministic tool writes a file under `story/` for legacy authority. | `remove` | Replace entity/world/relation/hook edits with typed Runtime diff commands. |
| `inkos/packages/studio/src/api/server.ts` Truth and chapter handlers | Direct filesystem write surface. | `remove` | See Studio route inventory below. |

## 2. Markdown bootstrap entry points

| Code/path | Current behavior | Classification | Required Phase 8 action |
|---|---|---|---|
| `inkos/packages/core/src/state/runtime-state-store.ts:loadRuntimeStateSnapshot` | Always calls `bootstrapStructuredStateFromMarkdown()` before reading JSON state. | `remove` | Runtime operation must never infer authority from Markdown. |
| `inkos/packages/core/src/state/state-bootstrap.ts:bootstrapStructuredStateFromMarkdown` | Creates structured JSON when files are absent. | `retain as importer` | Move behind the explicit migration adapter; no normal-runtime import. |
| `inkos/packages/core/src/state/state-bootstrap.ts:rewriteStructuredStateFromMarkdown` | Rewrites structured state from Markdown. | `retain as importer` | Remove from pipeline settlement and expose only through migration preview/confirm. |
| `inkos/packages/core/src/pipeline/runner.ts:syncLegacyStructuredStateFromMarkdown` | Normal write/revise/repair/import flow invokes Markdown-to-JSON sync. | `remove` | No long-form normal-runtime caller may remain. |
| `loadSnapshotCurrentStateFacts()` Markdown fallback | Parses a snapshot Markdown file when structured snapshot JSON is absent. | `deprecate` | Legacy reader may use it read-only during support window; it cannot write authority. |
| `StoryRuntime migration_jobs.py` Markdown parsing | Converts legacy Markdown into CIR with provenance. | `retain as importer` | Keep source read-only, explicit and checksummed. |

There must be no startup, read, compose, write, doctor, or repair path that automatically invokes a Markdown importer after cutover.

## 3. Old JSON StateManager write entry points

| Code/path | Current behavior | Classification | Required Phase 8 action |
|---|---|---|---|
| `inkos/packages/core/src/state/manager.ts` chapter index/snapshot/truncate helpers | Persists long-form progress and recoverable story state in files. | `remove` | Replace long-form progress reads with Runtime status/projections. |
| `inkos/packages/core/src/state/runtime-state-store.ts` manifest/current-state/hooks/summaries writes | Persists a second structured state source. | `retain as projection` | Projection output must be revision/checksum-bound and rebuildable. |
| `webnovel-writer/.../state_manager.py` (`_save_state`, `save_state`) | Writes `.webnovel/state.json` and best-effort SQLite mirror data. | `retain as importer` | Do not package as a writer; parser/mapping only. |
| `webnovel-writer/.../sql_state_manager.py` | Direct legacy `index.db` mutation. | `retain as importer` | Read-only source interpretation only; Runtime repository owns new writes. |
| InkOS book/project configuration in `book.json`/`inkos.json` | Product settings, provider selection and non-story metadata. | `unknown` | Separate configuration ownership from canon fields before deleting StateManager wholesale. |

## 4. InkOS `memory.db` long-form writes

| Code/path | Current behavior | Classification | Required Phase 8 action |
|---|---|---|---|
| `inkos/packages/core/src/state/memory-db.ts` | Opens `story/memory.db` with `node:sqlite` and mutates facts/hooks/summaries. | `remove` | Delete from long-form runtime and public long-form exports. |
| `runner.ts:syncNarrativeMemoryIndex`, `rebuildNarrativeMemoryIndex`, fact-history sync | Rebuilds/writes memory DB after chapter, revision, repair, resync and import. | `remove` | Composer uses Runtime query APIs only. |
| `utils/memory-retrieval.ts` | Reads the long-form memory DB for context. | `remove` | Use Runtime exact query/retrieval DTOs. |
| `migration_jobs.py` handling of `memory.db` | Treats it as candidate evidence, never winner by default. | `retain as importer` | Preserve read-only evidence provenance. |
| `play/play-db.ts` and `play/play-db-factory.ts` | SQLite state for Play sessions, not long-form canon. | `retain for non-long-form` | Protect with a separate root/config/ADR and architecture-test exemption. |

## 5. Studio Truth/raw authority routes

| Route/code | Current behavior | Classification | Required Phase 8 action |
|---|---|---|---|
| `PUT /api/v1/books/:id/truth/:file` (`server.ts`) | Directly replaces a Truth/control file; Runtime books are currently rejected. | `remove` | Entity/world/relation/hook edits become typed Runtime diff commands with expected revision and five metadata fields. Markdown edits remain drafts/proposals only. |
| `PUT /api/v1/books/:id/chapters/:num` | Direct chapter file replacement on legacy books. | `remove` | Route to Runtime revision/commit command or return legacy read-only migration guidance. |
| `POST .../repair-state/:chapter`, `.../resync/:chapter`, `.../rewrite/:chapter`, `.../import/chapters`, `.../import/canon` | Invokes legacy long-form file settlement. | `remove` or `retain as importer` | Import routes move to migration jobs; rewrite/repair/resync use Runtime commands. |
| `PUT /api/v1/project/artifacts/:file` | Generic project artifact write. | `unknown` | Prove it cannot reach `books/*/story`, Runtime data, snapshots or migration data before retention. |
| Raw Runtime database download | No such Studio route was found in the current route inventory. | `retain as projection` | Keep absent; exports use API DTO/snapshot, never raw SQLite. |
| Runtime migration/recovery/review proxy routes | Proxy versioned Runtime APIs and do not open SQLite. | `retain as projection` | Keep schema validation, authorization and redaction. |

Required command path:

`typed diff command -> Runtime validation -> expected revision -> transaction -> event -> projection`.

## 6. Agent file-write tools

| Tool/code | Current behavior | Classification | Required Phase 8 action |
|---|---|---|---|
| `write_truth_file` / `createWriteTruthFileTool` | Replaces `story/` files. | `remove` | Do not register for any long-form session. |
| `edit` / `createEditTool` | Exact replacement anywhere under `books/`; only Runtime-authority books are blocked. | `remove` | Long-form sessions receive no generic writer, including unmigrated legacy books. |
| `write` / `createWriteFileTool` | Creates/overwrites files under `books/`; only Runtime-authority books are blocked. | `remove` | Split non-long-form artifact tools from long-form tools and enforce roots in code. |
| `patch_chapter_text`, `replace_chapter_text`, rename tools | Mutate legacy chapter/Truth files through project tools. | `remove` | Replace with typed revision/entity commands; an Agent only proposes. |
| `import_chapters` | Invokes legacy long-form import and state reconstruction. | `retain as importer` | Agent may request a migration dry-run, but may not execute cutover or write source. |
| `read`, `grep`, `ls` | Read below configured project roots. | `deprecate` | Retain only through an allow-listed context broker; Runtime data and migration snapshots must be denied by canonical path. |
| Play/Film authoring tools | Write their own non-long-form stores. | `retain for non-long-form` | Register only in Play/Film sessions and never share a long-form writable root. |

Current safeguards check `book.authorityMode === "runtime"`; that is insufficient for Phase 8 because an unmigrated legacy book must also be read-only. Security must be enforced by tool construction and canonical path capabilities, not prompt text or Claude hooks.

## 7. Legacy chapter persistence entry points

| Entry | Classification | Required Phase 8 action |
|---|---|---|
| `LegacyChapterPersistence` | `remove` | Delete after actual-project cutover acceptance. |
| `persistChapterArtifacts()` | `remove` | No long-form authority caller remains. |
| `WriterAgent.saveChapter()` calls in draft/import/repair/revise paths | `remove` | Generated body stays transient until Runtime prepare/validate/commit. |
| `StateManager.saveChapterIndex`, snapshot and truncate flows | `remove` | Replace with Runtime status/snapshot/restore. |
| CLI/TUI/Studio legacy `write`, `rewrite`, `approve/reject`, `repair`, `resync`, `import` callers | `remove` or `retain as importer` | Unmigrated project: read/export/dry-run/backup only. |
| Runtime `StoryRuntimeChapterPersistence` | `retain as projection` | This is the sole long-form commit adapter; Runtime remains the writer. |

## 8. webnovel Dashboard and Claude plugin runtime

| Path | Classification | Required Phase 8 action |
|---|---|---|
| `webnovel-writer/webnovel-writer/dashboard/**` | `remove` | Exclude from final product/runtime packaging; Studio Runtime panel is the single status UI. |
| `webnovel-writer/.claude-plugin/**` | `remove` | Exclude plugin marketplace/runtime entry points. |
| `webnovel-writer/webnovel-writer/hooks/**` | `remove` | Claude hook is not a security boundary. |
| `webnovel-writer/webnovel-writer/skills/**` and `agents/**` | `remove` | Do not ship as a second writing runtime; retain only upstream history/reference fixtures where licensing allows. |
| Upstream clone, Git history, LICENSE and provenance mapping | `retain as importer` | Preserve source history and license evidence; do not erase provenance. |

## 9. JSON event/commit authority

| Path | Current behavior | Classification | Required Phase 8 action |
|---|---|---|---|
| webnovel `.story-system/commits/*.commit.json` writers | Persists a legacy commit authority before/around projections. | `remove` | Runtime SQLite commit/event transaction is the only authority. |
| webnovel `event_log_store.py` | Writes JSON events then mirrors to `index.db`. | `remove` | No JSON-first append or SQLite mirror dual-write. |
| webnovel `projections.py`, projection log and retry writers | Replays legacy commit files into multiple stores. | `retain as importer` | Only source parsing/mapping behavior may remain; Runtime replay is canonical. |
| Runtime event store, commit tables and core projections | Transactional Runtime authority. | `retain as projection` | Retain as the sole authority/event/projection engine. |
| InkOS interaction/Play/session event JSON | Product/session or non-long-form state, not proven long-form canon. | `unknown` | Separate namespace and schema before any deletion. |

## 10. Direct SQLite access

| Caller | Database | Classification | Required Phase 8 action |
|---|---|---|---|
| `hybrid/story-runtime/src/story_runtime/**` repository/services | Runtime authority SQLite. | `retain as projection` | Access remains inside Runtime only. |
| InkOS `state/memory-db.ts` and `memory-retrieval.ts` | Long-form `story/memory.db`. | `remove` | No TypeScript long-form SQLite access. |
| InkOS Play DB modules | Play session DB. | `retain for non-long-form` | Explicit ADR, separate root and architecture exemption. |
| Story Runtime `migration_jobs.py` | Read-only legacy SQLite plus Runtime-owned import transaction/snapshot. | `retain as importer` | Keep provenance and immutable/read-only source connection. |
| webnovel `index_manager.py`, `sql_state_manager.py`, `rag_adapter.py`, Dashboard | `index.db`/`vectors.db`. | `remove` or `retain as importer` | No packaged writer/UI; read-only parser or algorithm provenance only. |
| InkOS Studio | No direct Runtime SQLite open found. | `retain as projection` | Add a CI gate to keep it that way. |

## 11. Hidden compatibility fallbacks

| Fallback | Classification | Required Phase 8 action |
|---|---|---|
| `storyRuntime.mode = legacy` | `deprecate` | Unmigrated long-form is read-only; it cannot select a legacy writer. |
| `storyRuntime.mode = shadow` | `remove` | Diagnostic dual-read must not survive final cutover as a hidden writing source. |
| `fallbackOnUnavailable` to `LegacyTruthContextProvider` | `remove` | Runtime-authority writing fails closed; no Truth fallback. |
| Node SQLite unavailable -> Markdown memory fallback | `remove` | Long-form context always comes through Runtime API. |
| automatic Markdown structured-state bootstrap | `remove` | Explicit importer only. |
| new outline path -> `story_bible.md`/legacy outline fallback | `deprecate` | Read-only display/import support may remain for a dated window. |
| Studio legacy shim files (`story_bible.md`, `book_rules.md`) | `deprecate` | Read-only compatibility projection; no writes. |
| `inputGovernanceMode = legacy` | `unknown` | It may be prompt-composition compatibility rather than authority; prove no write-path impact before removal. |
| `session-transcript-legacy.ts` and BookSession lazy migration | `unknown` | Conversation history is not story authority, but callers and retention policy need separate analysis. |

## 12. Play, Short Fiction and Interactive Film boundary

| Feature | State implementation | Classification | Boundary requirement |
|---|---|---|---|
| Play | `play/play-db.ts`, `play-store.ts`, Play tools/routes. | `retain for non-long-form` | Own database/root/schema; never import long-form Truth/StateManager writer or share Runtime authority paths. |
| Short Fiction | `pipeline/short-fiction-runner.ts`, `agents/short-fiction.ts`, output package files. | `retain for non-long-form` | Standalone package files are final artifacts, not long-form canon. Generic file tools must be scoped to its output root. |
| Interactive Film | `interactive-film/graph-store.ts`, `authoring-store.ts`, export modules and film tools. | `retain for non-long-form` | Own graph/authoring state and typed tools; no long-form Truth compatibility code. |
| Translation | Separate translation project/run stores and EPUB/text exports. | `retain for non-long-form` | Keep outside long-form authority paths. |
| Shared `StateManager`, generic Agent tool arrays, session tooling | Some code is shared across session kinds. | `unknown` | Split capabilities by session kind before removing legacy long-form code. |

An ADR is required before deletion, recording each non-long-form data owner, root, database/file schema, tool capability set, backup/export behavior, and explicit non-authority relationship to Story Runtime.

## 13. Delete versus importer boundary

### Delete after the gate passes

- InkOS `LegacyChapterPersistence` and `persistChapterArtifacts()` as long-form commit paths.
- Long-form Truth/structured-state/memory writers and all normal-runtime Markdown bootstrap calls.
- Studio direct chapter/Truth mutation routes.
- Long-form Agent truth/file/chapter mutation tools and generic file-write capability.
- InkOS long-form `memory.db` access.
- webnovel Dashboard, Claude plugin/hooks/skills runtime, JSON-first commit/event writers, SQLite mirror writers and duplicate doctor/status UI.
- `legacy`, `shadow`, writer fallback and Markdown memory fallback modes for long-form execution.

### Retain only in the legacy importer/reader

- Markdown/JSON/state/contract/chapter parsers.
- Read-only `memory.db`, `index.db`, `vectors.db` evidence readers.
- CIR mapping, conflict resolution, checksums, source provenance, snapshot/rollback and cutover workflow.
- Legacy read-only viewer, backup and export support for unmigrated projects.
- Upstream history, source references and license/provenance records.

### Forbidden to delete now (`unknown`)

- Mixed-responsibility portions of `StateManager` that may own application configuration rather than story canon.
- Generic project artifact PUT until its reachable roots are proven.
- `inputGovernanceMode=legacy` until authority impact and callers are inventoried.
- legacy session transcript migration and BookSession compatibility code.
- shared Agent/session tooling used by Play/Short/Film.
- interaction/session event files until their relationship to long-form authority is proven.

## 14. Export formats to retain

| Format/artifact | Classification | Final rule |
|---|---|---|
| Chapter Markdown and full-book Markdown | `retain as projection` | Generated from a pinned Runtime revision with checksum; edits do not auto-import. |
| TXT export | `retain as projection` | Generated from Runtime chapter query/snapshot, not legacy chapter files as authority. |
| EPUB | `retain as projection` | InkOS formatting remains; input is a revision-consistent Runtime export. |
| Human-readable state/current-status snapshot | `retain as projection` | Explicitly marked non-authoritative and rebuildable. |
| Runtime snapshot/backup | `retain as projection` | Verified, revision-bound recovery artifact; mutation only via restore command. |
| Migration report, CIR decision log and source checksum manifest | `retain as importer` | Preserve provenance and rollback evidence. |
| Raw Runtime SQLite download | `remove` | Do not expose through Studio/product APIs. |
| Play/Short/Film/Translation exports | `retain for non-long-form` | Remain under their independent data ownership ADR. |

## Static/dead-code inventory status

The route inventory and targeted import/text scans were completed for the categories above. Destructive unused-export/dead-code cleanup was intentionally not run because the Phase 7 gate failed and current Phase 7 work is uncommitted. No claim is made that code is dead merely because a text search found no caller. After gate approval, Phase 8 must run TypeScript unused-export analysis, Python dead-code/import graph analysis, route/test/flag/config inventories, then delete in small batches with a full test run after each batch.

## Decision

`BLOCKED_NO_ACTUAL_PROJECT_MIGRATION_EVIDENCE`

No item classified `remove` may be changed in this phase attempt. No item classified `unknown` may be deleted under any circumstance until a follow-up audit resolves its owner and callers.
