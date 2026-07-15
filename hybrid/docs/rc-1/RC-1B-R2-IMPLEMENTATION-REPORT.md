# RC-1B-R2 Implementation Report

Date: 2026-07-15 (Asia/Shanghai)

## Result

F-001 is closed for the Runtime Writer path.

## Original and replacement call chains

Original:

`PipelineRunner._writeNextChapterLocked()` -> `WriterAgent.writeChapter()` ->
`WriterAgent.loadRecentChapters()` -> local `readdir/readFile chapters/*.md`.

Replacement:

`PipelineRunner` -> Runtime status revision `R` ->
`ProjectWriterNarrativeContextResolver` ->
`StoryRuntimeWriterNarrativeContextAdapter` ->
`ChapterApplicationService.exportSnapshot(expectedRevision=R)` -> Runtime
chapter export -> typed `WriterNarrativeContext` -> `WriterAgent`.

## Authority and DTO

Authority is resolved once by `ProjectWriterNarrativeContextResolver`. Runtime
uses `StoryRuntimeWriterNarrativeContextAdapter`; legacy uses
`LegacyWriterNarrativeContextAdapter`. The DTO includes project ID, authority,
project revision, latest chapter, ordered recent chapters, summary, full body,
body checksum, finalized revision, previous ending, and source.

Runtime adapter failures are fail-closed. It has no local fallback, merge mode,
or Runtime SQLite access. Legacy local reads remain available only through the
explicit legacy chapter export adapter.

## Runtime contract change

Context query accepts `expected_revision`; Runtime validates it before context
assembly and checks revision again before responding. The JSON Schema, Pydantic
model, TypeScript client, unit test, and contract test were updated. Existing
revision-bound chapter export supplies ordered body/summaries/checksums, so no
new chapter endpoint was required.

## Removed or restricted local reads

Removed: `WriterAgent.loadRecentChapters()` and its `readdir/readFile` chapter
body path. Writer no longer reads `story/chapter_summaries.md`; recent summaries
come from the injected DTO. English variance and Runtime long-span fatigue now
consume DTO bodies. Composer suppresses duplicate Runtime recent-narrative
prompt entries.

## Prompt and gate

Book prompts are mode-specific. Runtime prompts say Story Runtime owns chapter
capability; local index/Markdown is legacy/importer-only. The AST gate now
covers Writer and verifies the revision-bound injection and Runtime-to-legacy
separation.

## Red team and regression results

The A-F local-source red team passed with Runtime revision 7 and a deterministic
Writer input stub. Runtime unavailable fails closed. Full regression passed:

- Story Runtime: 113 tests.
- Core: 1,570 tests.
- Studio: 503 tests.
- CLI/TUI: full package suite passed.
- Core typecheck and Runtime architecture check passed.
- After the final recovery-entry DTO threading change, 38 focused Core tests,
  Core typecheck, and the AST gate were rerun and passed.
- Runtime chapter reads, commit contract, Composer/context provider,
  ChapterApplicationService, PipelineRunner-adjacent Writer preparation,
  Continuity, export, analytics, CLI, Studio API, TUI, and architecture gate
  are included in those suites.

The existing product A-F projection matrix is also exercised by the Runtime
chapter service and Studio/CLI/TUI suites. Browser DOM and interactive TUI fault
matrices remain RC-1 verification work, not an F-001 ownership exception.

## Unverified items

No real LLM was invoked by the new red-team test. The requested Runtime Writer
input was captured by a deterministic stub. This task did not execute RC-1D,
RC-2 revision history, comprehensive sidecar work, or security-phase work.

## Git status

`master...origin/master` remains intentionally dirty with pre-existing RC-1
changes. Final status count: 59 modified tracked paths and 16 untracked paths
(75 entries total). This task's status entries include the Runtime context
schema/Pydantic/service files; Writer, Runner, Composer, context provider,
client, fatigue and recovery files; prompt/session files; tests and AST gate;
new `writer-narrative-context.ts`; and the five RC-1B-R2 documents. No existing
dirty change was reverted.

F-001 CLOSED
RC-1B-R2 IMPLEMENTATION COMPLETE
