# RC-1 Gate Failure Report

## 1. Executive Summary

**RC-1 GATE FAILED**

The Runtime read adapter, API routes, CLI commands, export snapshot, analytics API, and six local-projection black-box cases are substantially working in the current worktree. However, a Runtime-authority write path still reads local chapter Markdown directly:

`PipelineRunner._writeNextChapterLocked()` -> `WriterAgent.writeChapter()` -> `WriterAgent.loadRecentChapters()` -> `readdir/readFile books/<id>/chapters/*.md`.

The runner establishes `authorityMode === "runtime"` before taking that path. Thus a Runtime project can use stale, missing, or locally injected chapter bodies to influence the next product chapter. This is an Architecture Failure, not a route-level bug. The new AST authority gate passes because it does not include `agents/writer.ts`; its pass is not sufficient evidence.

The required full browser/TUI black-box matrix is also absent, and RC-1 CI is not multi-platform or a release dependency. Those are Verification Gaps, but they do not reduce the architecture blocker.

Recommended next action:

`RETURN TO RC-1B`

## 2. Baseline

See [RC-1-GATE-FAILURE-BASELINE.md](RC-1-GATE-FAILURE-BASELINE.md). The assessment is against dirty `master@848cdd0d142067d01ec36f5bba0f85b59584e974`; 52 dirty/untracked entries include the implementation, tests, gate, workflow, and RC-1 documents under review.

Runtime fixture used for black-box execution: authority `runtime`, revision `7`, finalized chapters `1..3`, latest `3`, contract `story-runtime/v1`, Runtime `0.1.0`, DB schema `7`.

## 3. Gate-by-Gate Results

| Gate | Verdict | Evidence and conclusion |
|---|---|---|
| 1. Runtime owns chapter lists | **NOT VERIFIED** | Studio API and CLI returned `3/3/rev7` in all six cases; TUI has only a narrow renderer test and Studio browser pages have no RC-1 Chromium test. More importantly, Runtime writing still reads local recent chapter bodies (F-001), so product chapter inputs are not Runtime-only. |
| 2. Unified application service | **NO** | Studio routes call `createChapterService()`; CLI chapter/status/analytics/export and TUI `chapter-surface.ts` construct `ChapterApplicationService -> ProjectChapterAuthorityResolver`. But the Runtime write path bypasses the service and directly reads Markdown through `WriterAgent`. |
| 3. Analytics Runtime-only | **YES (current read surfaces)** | `StoryRuntimeChapterReadAdapter.analytics()` calls `assertCompatible()` then `chapterAggregate()`; Studio `/analytics`, CLI `stats`, and Core matrix returned Runtime count/revision. No local analytics cache was read in cases A-F. |
| 4. Export fixed Runtime revision | **YES (current read surfaces)** | Export routes call `exportSnapshot`; Runtime targeted tests validate pagination, expected revision, checksum mismatch, and concurrent commit snapshot. CLI and Studio exports in A-F contained Runtime body only and carried revision 7. |
| 5. Delete local projection | **NOT VERIFIED** | Cases A-F actually deleted/isolated Markdown, index, analytics cache, search index, and export cache in a temporary project. CLI and Studio API reads passed. Browser Studio pages and interactive TUI browser/detail were not exercised; `WriterAgent` still makes chapter Markdown an input during Runtime writing. |
| 6. Runtime unavailable never falls back | **NOT VERIFIED** | CLI list/export failed closed for connection refused, timeout, degraded health, malformed DTO, version mismatch, authorization, and DB lock. No local fake was returned and an old export sentinel was not overwritten. Studio/TUI error presentation and write blocking under every fault were not black-box tested. |
| 7. No reachable second fact source | **NO** | F-001 is a reachable Runtime-authority local Markdown reader. Resolver protections prevent `LegacyChapterReadAdapter` for regular read surfaces, but do not cover `WriterAgent`. |
| 8. Formal CI gate | **NO** | Committed workflow exists and last default-branch run passed, without `continue-on-error`; it is Linux-only, the fuller dirty workflow is uncommitted/unrun, branch-protection status is unknown, and release workflow does not depend on the RC-1 gate. |

### Actual Unified Read Call Chain

`Studio API / CLI command / TUI chapter action` -> `ChapterApplicationService` -> `ProjectChapterAuthorityResolver.resolve()` -> for `book.authorityMode === "runtime"`, only `StoryRuntimeChapterReadAdapter` -> `StoryRuntimeClient.assertCompatible()` -> Runtime chapter endpoint.

The normal read chain is supported by `chapter-application-service.test.ts` (13 tests), Studio `server.test.ts` (131 tests), CLI/TUI targeted tests (10 tests), the AST gate (438 modules), and the fresh fixture matrix. It does not govern `WriterAgent`.

## 4. Black-box Matrix

Legend: **P** = executed and passed through a fresh Runtime + Studio API + new CLI process; **P(API)** = Studio server API exercised, not browser DOM; **NV** = not verified at the requested black-box surface. All P/P(API) cells returned Runtime revision 7 / chapters 1-3, did not return local chapter 4/latest 99/conflicting body, and export contained Runtime body.

| Case | Studio home | Studio list | Studio detail | Studio analytics | Studio export | CLI list | CLI show | CLI stats | CLI export | TUI browser | TUI detail | Search | Project reopen |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A: no index, no Markdown | P(API) | P(API) | P(API) | P(API) | P(API) | P | P | P | P | NV | NV | P(API)+P | P (fresh CLI) |
| B: index says 0 | P(API) | P(API) | P(API) | P(API) | P(API) | P | P | P | P | NV | NV | P(API)+P | P (fresh CLI) |
| C: index says 2 | P(API) | P(API) | P(API) | P(API) | P(API) | P | P | P | P | NV | NV | P(API)+P | P (fresh CLI) |
| D: index says 4 + local chapter 4 | P(API) | P(API) | P(API) | P(API) | P(API) | P | P | P | P | NV | NV | P(API)+P | P (fresh CLI) |
| E: local chapter 2 checksum differs | P(API) | P(API) | P(API) | P(API) | P(API) | P | P | P | P | NV | NV | P(API)+P | P (fresh CLI) |
| F: local latest is 99 | P(API) | P(API) | P(API) | P(API) | P(API) | P | P | P | P | NV | NV | P(API)+P | P (fresh CLI) |

Representative observed values: CLI list `3/3/7`; CLI show chapter 2 checksum `b8ea99...c1fa`; CLI stats `3/7`; CLI export `chaptersExported=3`, `projectRevision=7`; Studio home `chaptersWritten=3`; Studio list `3/3/7`; Studio analytics `3/7`; Studio search `1/7`; Studio export contained `运行时正文`.

## 5. Static Call Graph Findings

| Match family / paths | Classification | Result |
|---|---|---|
| `ChapterApplicationService`, resolver, Runtime adapter | Runtime authority reachable | Correct normal read boundary. |
| `StateManager.loadChapterIndex`, `chapters/index.json`, durable story progress | legacy only | Resolver uses these only through `LegacyChapterReadAdapter`; Runtime resolver does not choose it. |
| `state/manager.ts ensureRuntimeState` | projection only | Explicitly throws; no Markdown bootstrap occurs. |
| `interaction/edit-controller.ts` local chapter reader | legacy only | Rejects Runtime authority before local edit/read transaction. |
| `agent/agent-tools.ts` read/grep | Runtime authority reachable, guarded | Runtime chapters route to service search/get; local story projection is rejected. |
| `agents/continuity.ts` previous chapter reader | legacy only | `isRuntimeAuthorityBook()` makes previous chapter empty and skips local truth reads. |
| `agents/writer.ts loadRecentChapters` | **Runtime authority reachable** | No guard; called by Runtime `PipelineRunner` before writing. Finding F-001. |
| `agent-system-prompt.ts` references `chapters/index.json` | documentation drift / unknown policy impact | Prompt still instructs the agent about local chapter index. It should be removed or scoped to legacy/import operations. |
| `memory.db` / local analytics reader / local export body reader | projection only or no production chapter-reader match | No reachable Runtime analytics/export body read was found; Runtime export uses `chapterExport`. |
| legacy adapter / migration scanner | importer only / legacy only | Retained for migration and legacy projects; no evidence that resolver selects it for a Runtime book. |
| tests and docs | test only / documentation only | Excluded from product reachability determination. |

## 6. Runtime Unavailable Findings

Fault fixture used Case D local fake chapter 4 and a pre-existing export sentinel. For every row, CLI list and export exited nonzero, no fake local chapter was returned, and the sentinel was not overwritten.

| Fault | Observed error | Local fallback | Old export |
|---|---|---|---|
| connection refused | `Story Runtime is unavailable: fetch failed` | none | preserved |
| timeout | `Story Runtime is unavailable: AbortError` | none | preserved |
| health degraded | `Runtime is not ready: status=degraded, database=migration_required` | none | preserved |
| malformed DTO | schema validation error | none | preserved |
| version mismatch | HTTP 409 `VERSION_MISMATCH` | none | preserved |
| authorization failure | `rejected the configured credentials` | none | preserved |
| DB locked | HTTP 423 `DATABASE_LOCKED` | none | preserved |

Not black-box verified: Studio/TUI visible error handling and write rejection for every fault mode. This is F-003, not proof of fallback.

## 7. Export Findings

`StoryRuntimeChapterReadAdapter.exportSnapshot()` calls compatibility handshake then `StoryRuntimeClient.chapterExport()`. `interaction/export-artifact.ts` is checked by the AST gate for absence of filesystem readers and required `exportSnapshot()` usage.

Runtime tests `test_chapter_reads.py` passed: fixed-revision pagination, aggregate/search body backing, expected revision/checksum rejection, and export snapshot while a concurrent commit finishes. Fresh Case A-F Studio and CLI exports used Runtime bodies. No export architecture defect was found.

## 8. Analytics Findings

`StoryRuntimeChapterReadAdapter.analytics()` calls Runtime `chapterAggregate()` and returns `stale: false`; Studio `/api/v1/books/:id/analytics` and CLI `stats` call the service. Fresh cases A-F kept chapter count 3 and revision 7 despite deleted/stale local cache/index states. No analytics cache fallback was found.

## 9. CI Findings

The committed RC-1 workflow has a successful default-branch run but is insufficient as a formal release gate: Ubuntu only; no Windows/macOS coverage; no demonstrated branch-protection requirement; no `needs: authority-gate` from `release.yml`; and the expanded current workflow is dirty/uncommitted/unrun. Chromium ran locally (15/15), but all 15 tests target other Studio features, not RC-1 long-form authority UI.

## 10. Root Causes

1. The authority boundary was applied to product read routes but not to the Runtime writing/agent input path. `WriterAgent` retained a legacy Markdown recent-chapter helper and `PipelineRunner` still invokes it after Runtime authority is selected.
2. The AST gate enumerates selected roots but omits `agents/writer.ts`, so it cannot detect the reachable local body reader.
3. RC-1 verification overstates service/API test coverage as product black-box coverage; browser TUI and Studio authority pages are not in the Chromium suite.
4. CI implementation and docs are ahead of the commit/required-release configuration.

## 11. Blockers

- **F-001 (blocker, Gate 7, Architecture Failure):** Runtime-authority writer directly reads local chapter Markdown.
- **F-002 (major, Gate 8, Verification Gap):** RC-1 architecture gate is not a proven multi-platform, required release dependency.
- **F-003 (major, Gates 1/5/6, Verification Gap):** Required browser Studio and interactive TUI deletion/fault matrix is missing.
- **F-004 (minor, Gate 7, Documentation Drift):** Agent prompt still tells users/agents that `chapters/index.json` is the chapter index without a legacy-only qualification.

## 12. Required Fixes

### F-001

| Field | Detail |
|---|---|
| finding ID | F-001 |
| gate | 7 (also invalidates Gates 1 and 2 as a whole-system claim) |
| severity | blocker |
| failure type | Architecture Failure |
| affected surface | Runtime-authority chapter generation and recent-chapter context |
| actual behavior | Runtime runner calls WriterAgent, which reads local `chapters/*.md` without an authority check. |
| expected behavior | Runtime chapter bodies must enter writer context via a Runtime revision-bound capability/service only. Missing local projections must not alter generated chapter input. |
| reproduction | Configure Runtime book; seed Runtime chapters 1-3; add/alter local chapter Markdown; call `PipelineRunner.writeNextChapter`; trace `WriterAgent.loadRecentChapters`. |
| code path | `packages/core/src/pipeline/runner.ts:882`, `:940`; `packages/core/src/agents/writer.ts:151`, `:179`, `:1026`. |
| test evidence | Static trace above; current AST gate passes despite omission. Existing tests do not assert WriterAgent avoids local Markdown in Runtime mode. |
| root cause | Legacy helper retained outside the application-service boundary. |
| recommended fix | Redesign writer input so Runtime context/revision snapshot supplies recent bodies; prohibit filesystem chapter reads in Runtime writer path; add WriterAgent to architecture gate. |
| suggested stage | **RC-1B** |
| retest requirement | New Runtime writer fixture with absent/conflicting/local-extra bodies; assert a revision-bound Runtime request and zero local `readdir/readFile` calls; repeat all A-F surfaces. |

### F-002

| Field | Detail |
|---|---|
| finding ID | F-002 |
| gate | 8 |
| severity | major |
| failure type | Verification Gap |
| affected surface | release governance |
| actual behavior | Current committed workflow is Ubuntu-only and release has no dependency on it. |
| expected behavior | Required architecture gate runs on Windows/Linux/macOS and release is blocked by it. |
| reproduction | Inspect `.github/workflows/rc1-chapter-authority.yml` and `release.yml`; query run `29273890711`. |
| code path | `.github/workflows/rc1-chapter-authority.yml`, `.github/workflows/release.yml`. |
| test evidence | One committed Linux run success; local expanded workflow uncommitted. |
| root cause | CI rollout not completed as committed release policy. |
| recommended fix | Commit the full matrix, add OS matrix and branch-protection requirement, wire release `needs` to gate, run it from default branch. |
| suggested stage | RC-1D after F-001 architecture redesign |
| retest requirement | successful required runs on all three OSes and a release workflow run showing dependency. |

### F-003

| Field | Detail |
|---|---|
| finding ID | F-003 |
| gate | 1, 5, 6 |
| severity | major |
| failure type | Verification Gap |
| affected surface | Studio browser UI, interactive TUI, Runtime-fault user errors |
| actual behavior | API/CLI matrix is executed; no RC-1 browser DOM or interactive TUI matrix exists. |
| expected behavior | All 6 x 13 requested cells and fault presentation are reproducible in CI. |
| reproduction | Inspect 15 Chromium specs and TUI tests; none drives long-form Runtime-authority projection deletion cases. |
| code path | `packages/studio/e2e/*`, `packages/cli/src/__tests__/tui-chapter-surface.test.ts`. |
| test evidence | Chromium 15/15 passed, but none targets RC-1 long-form authority pages. |
| root cause | Test plan stops at API/service boundary. |
| recommended fix | Build a committed fixture orchestrator and Playwright/Ink test matrix for the specified cases. |
| suggested stage | RC-1D after F-001 architecture redesign |
| retest requirement | 78 black-box cells plus seven fault scenarios report in CI. |

### F-004

| Field | Detail |
|---|---|
| finding ID | F-004 |
| gate | 7 |
| severity | minor |
| failure type | Documentation Drift |
| affected surface | agent instructions |
| actual behavior | `agent-system-prompt.ts` states that the local chapter index/files are the chapter source. |
| expected behavior | Runtime projects must be told to use the Runtime chapter capability; local paths must be legacy/import-only. |
| reproduction | Search `agent-system-prompt.ts` for `chapters/index.json`. |
| code path | `packages/core/src/agent/agent-system-prompt.ts:513`, `:570`. |
| test evidence | Static search; no mode-specific prompt test. |
| root cause | Migration documentation was not updated with authority cutover. |
| recommended fix | Scope the text to legacy/importer mode and add a Runtime-mode prompt assertion. |
| suggested stage | RC-1D |
| retest requirement | Prompt/static test confirms no Runtime project receives local chapter-owner instructions. |

## 13. Recommended Next Stage

`RETURN TO RC-1B`

Reason: F-001 requires changing the ownership design of a Runtime-authority execution path and its read capability, not merely wiring an existing application service to one missed route. RC-1D may address the CI and test gaps only after the Runtime writer no longer reads local chapter bodies.

## 14. Retest Plan

1. Redesign the Runtime writer context API and remove/restrict direct Markdown recent-chapter reads for Runtime books.
2. Add a red-capable test that injects local fake chapter 4/conflicting chapter 2 and proves Runtime writer context remains revision-bound to 7 with no local reader invocation.
3. Extend the AST gate to cover `WriterAgent` and any agent/pipeline chapter body readers.
4. Commit a disposable fixture orchestrator; execute all Case A-F by Studio browser UI, API, CLI, TUI, search, export, and fresh reopen.
5. Add all seven unavailable modes to Studio, CLI, and TUI assertions, including no old-export overwrite and write rejection.
6. Commit CI changes; run the gate on Windows, Linux, and macOS; make the release workflow depend on the required gate.
7. Re-run all commands in the baseline and issue a new report from a clean, committed candidate.

```
RC-1 GATE FAILED

Recommended next action:
RETURN TO RC-1B
```
