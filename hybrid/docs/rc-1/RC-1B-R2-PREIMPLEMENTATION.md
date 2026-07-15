# RC-1B-R2 Preimplementation Review

Date: 2026-07-15 (Asia/Shanghai)

## Scope and baseline

This review was performed before the RC-1B-R2 implementation against the dirty
workspace described by `RC-1-GATE-FAILURE-BASELINE.md`. Existing RC-1 changes are
preserved. The task is limited to F-001, its directly required contracts, tests,
prompt text, and architecture gate.

## 1. How Runtime authority is determined

`PipelineRunner._writeNextChapterLocked()` loads `book.json` through
`StateManager.loadBookConfig()` and requires `book.authorityMode === "runtime"`.
It then requires a `story-runtime` connection, performs the compatibility
handshake, reads Runtime project status, and verifies
`status.authority_mode === "runtime"`. Regular chapter product reads resolve at
`ProjectChapterAuthorityResolver.resolve()`: Runtime books receive only
`StoryRuntimeChapterReadAdapter`; legacy books receive only
`LegacyChapterReadAdapter`.

## 2. Where WriterAgent loses authority context

The runner retains the Runtime status and revision, but the old
`WriteChapterInput` contains neither authority nor a revision-bound narrative
DTO. `WriterAgent.writeChapter()` therefore obtains prose independently by
calling `loadRecentChapters(bookDir, chapterNumber)` twice. That helper enumerates
and reads `books/<id>/chapters/*.md`. The English variance helper adds an indirect
second path through `buildEnglishVarianceBrief()` and
`loadPreviousChapterBodies()`. Neither read is bound to Runtime revision.

Original reachable chain:

`PipelineRunner._writeNextChapterLocked()` -> `WriterAgent.writeChapter()` ->
`WriterAgent.loadRecentChapters()` -> local `readdir/readFile`.

Indirect reachable chain:

`WriterAgent.writeChapter()` -> `buildEnglishVarianceBrief()` ->
`loadPreviousChapterBodies()` -> local `readdir/readFile`.

## 3. Callers of the local recent-chapter reader

`WriterAgent.loadRecentChapters()` has one production caller,
`WriterAgent.writeChapter()`, at two call sites (one-chapter creative context and
five-chapter fingerprint context). `utils/long-span-fatigue.ts` has separate
local body readers used by Writer English variance and PipelineRunner fatigue
analysis. Direct WriterAgent tests also exercise the legacy behavior.

## 4. Other Agents that read chapter Markdown

`ContinuityAuditor.loadPreviousChapter()` can read the previous Markdown chapter,
but `auditChapter()` checks `book.authorityMode` first and suppresses that read for
Runtime books. `ReviserAgent` reads local story projection files, not chapter
bodies, in the inspected path. Agent `read` and `grep` tools route Runtime chapter
reads through `ChapterApplicationService`; their local filesystem branches are
legacy-only. Composer does not read chapter Markdown. The unguarded Runtime
chapter-body readers found before implementation are WriterAgent and its
long-span-fatigue helper.

## 5. Existing Runtime recent-chapter capabilities

Runtime already exposes:

- project status with current revision and latest chapter;
- finalized chapter collection and detail;
- revision-checked chapter export (`expected_revision`) with full bodies,
  summaries, checksums, ordering, and each chapter's resulting revision;
- context query with a `recent_narrative` layer derived from chapter summaries
  and retrieval documents.

`ChapterApplicationService.exportSnapshot()` already validates the fixed Runtime
revision and body checksums. No TypeScript SQLite access is needed.

## 6. Does Composer already include recent narrative?

Yes. `StoryRuntimeContextProvider` maps Runtime context-query
`layers.recent_narrative` into `ContextPackage`. The Runtime layer currently may
contain five chapter summaries and excerpts from retrieval documents for the
latest prior chapter. It is prompt-oriented evidence, not the typed, ordered,
checksum-bearing chapter window needed by Writer post-write checks.

## 7. Duplicate injection risk

The governed Writer prompt receives Composer's `recent_narrative` through the
selected evidence block, while Writer separately loads local chapter bodies.
Legacy mode also combines a recent full-body block with the chapter summaries
projection. Thus the Runtime path currently duplicates recent narrative and can
mix conflicting sources. Memory/RAG remains relevant memory; hard constraints,
plot commitments, and style guidance remain separate layers.

## 8. Recommended single fix seam

Introduce one `WriterNarrativeContextPort` seam with two adapters:

- `StoryRuntimeWriterNarrativeContextAdapter` reads a fixed-revision export via
  the existing chapter application interface and fails closed;
- `LegacyWriterNarrativeContextAdapter` is the only module allowed to enumerate
  or read local chapter Markdown.

An authority resolver selects exactly one adapter. PipelineRunner obtains Runtime
revision R, asks the seam for the narrative window at R, passes the typed DTO to
WriterAgent, and uses R for prepare/validate/commit. WriterAgent only consumes the
DTO. Composer's Runtime recent-narrative prompt layer is suppressed on the write
path and the typed DTO is rendered once under the recent-narrative category.
Style fingerprints, previous ending, and fatigue checks consume the same DTO.
There is no Runtime-to-legacy fallback and no merged source mode.
