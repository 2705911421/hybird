# RC-2A.5 Decision Baseline

Captured: 2026-07-15T17:11:19+08:00
Decision scope: documentation and read-only verification only.

## Source and toolchain

| Item | Observed value | Evidence |
| --- | --- | --- |
| repository | `2705911421/hybird` | `origin=https://github.com/2705911421/hybird.git` |
| branch | `master` | tracks `origin/master` |
| commit | `cefed3baffacea6fce715b856cc89bdfeaabc521` | `close RC-1D after default-branch gate` |
| upstream | `0 ahead / 0 behind` | `git rev-list --left-right --count HEAD...@{u}` |
| tracked changes | none | `git diff --name-only` and cached diff were empty before this decision set |
| Node / pnpm | `v24.16.0` / `9.12.0` | local host; CI policy remains authoritative |
| Python / SQLite | `3.11.15` / `3.53.1` | local Runtime host |
| Runtime | `0.1.0` | `story-runtime/pyproject.toml`; `story_runtime.__version__` |
| InkOS | `1.7.0` | `inkos/package.json` |
| OpenAPI | `3.1.0`, document `0.7.0` | `contracts/story-runtime.openapi.yaml:1-4` |
| public contract | `story-runtime/v1` | `story_runtime/__init__.py:4` |
| DB migration | `7`, `phase9_scale_indexes` | `migrations.py:497-500` |
| current event schema | open `event_type`; nullable stored `schema_version` and `applied_revision`; new writes use `story-runtime/v1` | `migrations.py:54-65,198-202`; `chapter_commits.py:421-422` |
| reducer/projection version | none | reducer dispatch is code-only; checkpoints have no reducer version |
| authority modes | `legacy`, `runtime` | migration 2 check constraint; Runtime writes require `runtime` |

## Dirty worktree isolation

Before RC-2A.5 output, the worktree contained only the following untracked documentation. It was not cleaned:

- `hybrid/docs/rc-1/RC-1-FINAL-GATE-BASELINE.md`
- `hybrid/docs/rc-1/RC-1-FINAL-GATE-REPORT.md`
- `hybrid/docs/rc-1/RC-1-FINDING-REVALIDATION.md`
- `hybrid/docs/rc-1/architecture-classification/ARCHITECTURE-CLASSIFICATION-REVIEW.md`
- `hybrid/docs/rc-1/architecture-classification/AUDIT-CALLGRAPH.md`
- `hybrid/docs/rc-1/architecture-classification/BASELINE.md`
- `hybrid/docs/rc-1/architecture-classification/CLASSIFICATION-CRITERIA.md`
- `hybrid/docs/rc-2/AT-REVISION-AUDIT.md`
- `hybrid/docs/rc-2/EVENT-COVERAGE-MATRIX.md`
- `hybrid/docs/rc-2/HISTORICAL-DATA-MODEL-AUDIT.md`
- `hybrid/docs/rc-2/HISTORICAL-QUERY-API-DRAFT.md`
- `hybrid/docs/rc-2/RC-2-IMPLEMENTATION-PLAN.md`
- `hybrid/docs/rc-2/RC-2A-AUDIT-REPORT.md`
- `hybrid/docs/rc-2/RC-2A-BASELINE.md`

Impact: **low for architecture evidence, but provenance-sensitive**. No untracked document is treated as committed capability. All code/schema claims below were checked against tracked `HEAD`; this RC-2A.5 set itself remains documentation-only.

## Current architecture and sampled code facts

| Fact | Live-code sample | Decision impact |
| --- | --- | --- |
| `at_revision` is latest-only | `api.py:281-285` reads first, only rejects future; `services.py:62-64` and `repository.py:122-130` read current row | historical fallback to latest must be prohibited |
| no revision ledger | migration 1 has `projects.revision` but no revision table | Batch 1 must create the immutable manifest ledger |
| current tables overwrite | entities, relationships, timeline, threads and summaries have current PKs only; facts alone have validity columns | validity tables alone do not recover old history |
| imports bypass events | `migration_jobs.py:861-885` directly inserts every projection family; imported events/chapters increment by item | legacy projects require a bootstrap boundary unless authentic transitions are verified |
| operator event catalog is open | `api.py:357-360`; `chapter_commits.py:393-426` accepts arbitrary modeled event strings and dispatches by aggregate | closed catalog is a prerequisite |
| replay target is unsafe | `chapter_commits.py:351-376` clears current tables, filters prefix, copies all summaries, then checkpoints current project revision | target materialization must be isolated |
| reducers are unversioned and permissive | `chapter_commits.py:726-771` ignores event type and maps unknown aggregate to facts selection | unknown/version mismatch must fail closed |
| event store is not append-only | `story_events.project_id ... ON DELETE CASCADE`; recovery deletes at `chapter_commits.py:533` | Batch 2 must enforce append-only authority semantics |
| migration cutover is operational | `migration_jobs.py:252-270` changes authority mode without story revision/event | cutover audit and story bootstrap transition must be distinguished |

The lighthouse fixture independently confirms a populated project at revision 7 with two arbitrary events and no authentic transition sequence for revisions 0-6. It is evidence for limited history, not evidence for reconstructibility.

## RC-1 and CI state

RC-1 current-authority behavior is closed at this SHA; that establishes fail-closed current chapter reads, not historical reconstruction. Live `gh run list --commit` verification on 2026-07-15 found:

| Workflow | Run | Result |
| --- | ---: | --- |
| RC-1 Gate | `29389871238` | success |
| authority-gates | `29389871224` | success |
| phase9-cross-platform | `29389871215` | failure |

Repository CI is therefore **mixed / overall red**. Runtime matrices passed in the failing Phase 9 run, while Studio build, dependency security and Windows InkOS jobs failed as recorded in `RC-2A-BASELINE.md`. RC-2A.5 does not waive those failures and does not infer RC-2 readiness from RC-1.

## Baseline conclusion

The formal starting condition remains:

```text
HISTORICAL DATA NOT RECOVERABLE — LIMITED HISTORY DESIGN REQUIRED
```
