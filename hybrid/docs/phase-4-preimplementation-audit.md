# Phase 4 preimplementation audit

Date: 2026-07-12

This audit is based on the checked-out implementation, not only on the existing
architecture documents. Paths and line numbers refer to the Phase 3 repository
state immediately before Phase 4 business-code changes.

## 1. Current InkOS chapter write entry points

The long-form write surface is broader than `writeNextChapter()`:

- `PipelineRunner.writeNextChapter()` enters `_writeNextChapterLocked()` and
  calls `persistChapterArtifacts()` (`pipeline/runner.ts:1669,1697,2027`).
- `PipelineRunner.reviseDraft()` overwrites the chapter Markdown, current state,
  particle ledger, hooks, structured state, chapter index, snapshots and memory
  indexes directly (`pipeline/runner.ts:1318,1523-1592`).
- `repairChapterState()` and `resyncChapterArtifacts()` rewrite chapters, Truth,
  structured state, memory and indexes (`pipeline/runner.ts:2103-2203,2223-2352`).
- `importChapters()` writes every imported chapter, generated Truth, the chapter
  index and derived state (`pipeline/runner.ts:2733-2866`).
- earlier draft/save paths call `WriterAgent.saveChapter()` directly
  (`pipeline/runner.ts:1154`).
- CLI `write`, rewrite, review/reject/approve and import commands call these
  runner/state paths; review commands also update `chapters/index.json` directly.
- Studio exposes direct chapter save, approve/reject, revise/rewrite/resync,
  repair-state and import routes.
- natural-language tools expose `import_chapters`, `patch_chapter_text`,
  `replace_chapter_text`, `write_truth_file`, plus generic `edit` and `write`.

Runtime authority therefore cannot be implemented by changing only the normal
write-next-chapter path.

## 2. Pipeline flows that write chapters or Truth

`_writeNextChapterLocked()` reads Markdown Truth as validation authority, then
passes callbacks to `persistChapterArtifacts()`. Those callbacks execute, in
order, chapter Markdown save, Truth save, Markdown-to-JSON structured-state
sync, `memory.db` sync, chapter index save, audit drift writes, snapshot writes
and fact-history sync (`runner.ts:1950-2057`).

`reviseDraft()` independently overwrites both chapter and Truth files and then
re-snapshots (`runner.ts:1523-1592`). `repairChapterState()` and
`resyncChapterArtifacts()` repeat equivalent direct writes (`runner.ts:2186-2203,
2324-2352`). `importChapters()` is a separate multi-chapter write loop. Book
initialization also creates empty chapter indexes (`runner.ts:1001,1046`).

For Runtime authority, generated prose, audit output and state extraction may
remain in InkOS before commit, but every authoritative mutation above must be
routed through one persistence port. Export Markdown may only run after the
Runtime commit as a rebuildable projection.

## 3. `chapter-persistence.ts` call chain

The current chain is:

```text
CLI/TUI/Studio/agent
  -> PipelineRunner.writeNextChapter
  -> _writeNextChapterLocked
  -> Writer + Auditor + Reviser + StateValidator
  -> persistChapterArtifacts
     -> saveChapter (WriterAgent.saveChapter -> chapters/*.md)
     -> saveTruthFiles (WriterAgent.saveNewTruthFiles -> story/*.md)
     -> syncLegacyStructuredStateFromMarkdown (story/state/*.json)
     -> syncNarrativeMemoryIndex (story/memory.db)
     -> saveChapterIndex (chapters/index.json)
     -> snapshotState (story/snapshots)
     -> syncCurrentStateFactHistory
```

`persistChapterArtifacts()` has no transaction, revision compare-and-swap,
request identity, aggregate idempotency or durable state machine. Failure after
any callback leaves a visible partial result. Its tests explicitly assert this
callback ordering and old file writes.

## 4. Studio direct write APIs

`packages/studio/src/api/server.ts` contains these relevant routes:

- `PUT /api/v1/books/:id/chapters/:num` directly saves chapter text (line 2777).
- `PUT /api/v1/books/:id/truth/:file{.+}` directly writes Truth (line 5328).
- `POST .../repair-state/:chapter`, `.../revise/:chapter`,
  `.../rewrite/:chapter`, `.../resync/:chapter` invoke legacy runner writes.
- `POST .../chapters/:num/approve` and `/reject` mutate the legacy chapter
  index and rollback/snapshot state.
- `POST .../import/chapters` enters the legacy import chain.

Runtime authority must reject or route each mutation through the Runtime
adapter; read/export routes can remain dual-read/projection consumers.

## 5. Other CLI, TUI, agent and revision writes

CLI commands `write`, `revise`, `review`, `import`, `auto`, `audit` and book
maintenance instantiate `PipelineRunner` or `StateManager`. TUI slash commands
delegate into the same CLI/agent surfaces. Natural-language agent sessions
register deterministic book tools, including import and direct chapter/truth
edits. `reviseDraft()` is a distinct direct writer and is not covered by
`persistChapterArtifacts()`.

Runtime mode therefore needs enforcement below all command surfaces: project
authority resolution plus a persistence port and guards in direct file tools.

## 6. Agent tools with file-write capability

`agent/agent-tools.ts` exposes:

- `write_truth_file` through deterministic interaction tools (around line 2503);
- `patch_chapter_text` and `replace_chapter_text` (around 2562 and 2595);
- `import_chapters` (around 1173);
- generic `edit` and `write` under `books/` (around 2678 and 2723);
- other artifact writers such as report generation.

Prompt instructions prefer specialized tools but are not a security boundary.
Runtime authority requires code-level path classification: chapter and
authoritative Truth targets must not reach generic filesystem writes.

## 7. Current Runtime SQLite schema

Migrations currently create:

- infrastructure: `schema_migrations`, `idempotency_ledger`,
  `projection_checkpoints`, `runtime_incidents`;
- project and structured views: `projects`, `entities`, `relationships`,
  `timeline`, `narrative_threads`, `chapter_summaries`, `facts`;
- event/retrieval: `story_events`, `retrieval_documents`, `retrieval_fts` plus
  FTS maintenance triggers.

Missing Phase 4 aggregates are `chapter_commits`, `chapter_artifacts`,
`commit_transitions`, `outbox`, replay jobs and authority/cutover metadata.
Existing `story_events` and `projection_checkpoints` lack commit identity,
ordinal/revision, deterministic projection hash and complete replay metadata.

## 8. DTO sufficiency

The current prepare/validate/commit/append/replay contracts are useful seeds but
not sufficient:

- prepare has request/idempotency/revision/chapter intent, but no durable state
  result, payload hash semantics or authority/cutover response;
- artifacts include body, hash, events, outline fulfillment and an untyped
  review object, but omit summary, typed state mutation proposal, explicit
  evidence spans across all mutations and artifact checksum;
- events use `subject` rather than aggregate type/id and omit commit,
  chapter ordinal, schema version and deterministic-ID rules;
- validate has no structured severity/result or validation token response;
- commit has no finalized audit/result DTO;
- replay has a range and verify flag but no target revision, expected hash,
  dry-run result or replay job.

All write routes are currently deliberately mapped to
`WRITE_FEATURE_DISABLED` in `api.py`.

## 9. Reusable fixture transaction, idempotency and lock behavior

`StoryRepository.initialize_fixture()` already demonstrates a reusable local
pattern: one SQLite connection, `BEGIN IMMEDIATE`, lookup in the existing
`idempotency_ledger`, deterministic fixture loading, ledger result persistence
and one commit. `Database.connect()` centralizes foreign keys, WAL/busy timeout
and explicit connection close. Lock tests verify degraded health and restart
cleanup on Windows.

The reusable parts are connection configuration, `BEGIN IMMEDIATE`, the single
idempotency ledger and explicit close. Fixture-specific `INSERT OR IGNORE` is
not sufficient for chapter commits because it can hide conflicting payloads;
Phase 4 needs payload hashes and explicit conflicts.

## 10. Hidden dual-write paths

Confirmed dual/parallel authoritative writes include:

- chapter Markdown plus `chapters/index.json`;
- Markdown Truth plus `story/state/*.json` generated back from Markdown;
- current-state fact history and `memory.db` synchronization;
- snapshots that can later restore the file authority;
- Studio and agent direct edits that bypass the normal pipeline;
- revise, repair, resync and import paths that bypass
  `persistChapterArtifacts()`.

Runtime mode must not call these as authoritative writes. Post-commit Markdown
exports are allowed only if labeled/rebuildable and never read back as authority.

## 11. Chapter body storage decision

Phase 4 will store chapter bodies in SQLite `TEXT`, not an external blob store.
The approved contract currently caps a body at 200,000 characters; SQLite can
comfortably store this, and keeping body, events, projections, revision and
finalization in one transaction removes permanent-missing-blob and orphan-GC
states. A content-addressed blob store would add staging, verification, garbage
collection and Windows rename/lock recovery without a demonstrated size need.
`body_sha256` and artifact checksum will still provide content addressing and
integrity. A later storage change requires a separate migration/ADR.

## 12. Windows and filesystem risks

- Existing code has explicit Windows tests for process termination and SQLite
  connection cleanup; these patterns should be retained.
- Legacy writes use direct `writeFile` in several paths, while StateManager also
  has temporary-file/rename and lock-file logic. Antivirus/indexers can hold
  temporary or SQLite sidecar files, and rename semantics differ from POSIX.
- Deep `books/<id>/story/...` role/snapshot paths risk Windows path-length
  limits; Runtime authority avoids using those paths for canonical state.
- UTF-8 is explicit in most Node file calls and Python launchers use UTF-8, but
  CJK body/hash tests are required to ensure checksums use UTF-8 bytes.
- Runtime commits must rely on SQLite transaction/locking, not file existence,
  atomic rename or filesystem lock inference.

## 13. Tests coupled to legacy Truth authority

The principal coupled suites are:

- `chapter-persistence.test.ts`, which asserts chapter, Truth, index, snapshot
  and fact-history callback behavior;
- `pipeline-runner-memory-sync.test.ts`, which creates Markdown Truth and
  expects structured state/`memory.db` synchronization;
- `runtime-state-store.test.ts`, `state-manager.test.ts`, reducer/projection and
  snapshot tests, which treat `story/state` and Markdown as restorable state;
- `agent-tools.test.ts` and `agent-system-prompt.test.ts`, which assert direct
  `write_truth_file` behavior;
- Studio server tests for direct chapter/Truth PUT routes;
- CLI review/rewrite/import tests that inspect chapter files and indexes.

These remain valid legacy regressions. Runtime-authority tests must instead
assert that none of those authority writes occur, while optional exports remain
clearly non-authoritative.

## Audit decision

Phase 4 can proceed without dual authority only with these boundaries:

1. SQLite Runtime owns every canonical mutation for `authorityMode=runtime`.
2. InkOS performs LLM generation, audit, revision and typed extraction before
   the Runtime transaction, then submits one validated artifact aggregate.
3. The Runtime transaction persists body, events, all core projections,
   revision, audit transition and outbox atomically.
4. InkOS legacy persistence remains available only for
   `authorityMode=legacy` projects.
5. Shadow remains a context-read comparison mode and is not an authority mode.
6. Markdown/memory/search outputs after commit are disposable projections and
   are never ingested back into Runtime authority.
