# RC-2A Baseline

审计时间：2026-07-15（Asia/Shanghai）
审计范围：RC-2A 实施前只读审计；未修改业务代码、数据库 schema、事件模型或 UI。

## 1. Source baseline

| Item | Observed value | Evidence / interpretation |
| --- | --- | --- |
| repository | `2705911421/hybird` | `origin=https://github.com/2705911421/hybird.git` |
| branch | `master` | tracks `origin/master` |
| commit | `cefed3baffacea6fce715b856cc89bdfeaabc521` | `close RC-1D after default-branch gate` |
| upstream divergence | `0 ahead / 0 behind` | `origin/master...HEAD` |
| worktree | **dirty: 4 untracked paths** | listed below; no tracked diff |
| Node | `v24.16.0` | local audit host; CI uses Node 22 |
| pnpm | `9.12.0` | local audit host |
| Python | `3.11.15` | local audit host |
| SQLite | `3.53.1` | Python stdlib SQLite |
| OS | Windows 11 Home China, 64-bit, build `26200` | Python reports `Windows-10-10.0.26200-SP0` |
| InkOS version | `1.7.0` | `inkos/package.json` |
| Story Runtime version | `0.1.0` | `pyproject.toml`, `story_runtime.__version__` |
| OpenAPI document version | `0.7.0` | `hybrid/contracts/story-runtime.openapi.yaml` |
| public contract/schema | `story-runtime/v1` | `story_runtime.SCHEMA_VERSION` |
| SQLite migration | `7` / `phase9_scale_indexes` | last entry in `MIGRATIONS` |
| event schema | nullable `story_events.schema_version`; new writes use `story-runtime/v1` | bootstrap/old events can be `NULL` |
| projection/reducer version | **absent** | checkpoints store name/revision/hash, not reducer version |
| authority modes | `legacy`, `runtime` | DB constraint; RC-2 audits Runtime-authority projects |

### Dirty files

The following are untracked pre-existing RC-1 documents, not RC-2A output and not implementation evidence:

- `hybrid/docs/rc-1/RC-1-FINAL-GATE-BASELINE.md`
- `hybrid/docs/rc-1/RC-1-FINAL-GATE-REPORT.md`
- `hybrid/docs/rc-1/RC-1-FINDING-REVALIDATION.md`
- `hybrid/docs/rc-1/architecture-classification/`

Impact on audit: **low but explicitly isolated**. They do not overlap Runtime source, migrations, contracts, tests, or workflows. This audit uses `HEAD`, live tracked code, live tests and current GitHub Actions. None of these untracked documents is counted as an existing capability. The worktree was not cleaned.

## 2. RC-1 architecture state

At `HEAD`, RC-1 is closed for product chapter authority: Runtime-authority chapter list/detail/summary/search/analytics/export and Writer context flow through the Runtime application boundary and fail closed rather than silently falling back to local Markdown. The committed RC-1 workflow is now the full cross-platform, specialized-suite and Chromium matrix.

Current confirmation:

- GitHub Actions run `29389871238` for this exact SHA completed successfully.
- Its Windows, Ubuntu and macOS cross-platform jobs, specialized authority suites, Chromium UI black-box job and `RC-1 Required Gate` all succeeded.
- RC-1 does **not** establish RC-2 historical semantics. It proves current Runtime authority and fail-closed product reads only.

## 3. Current CI state

CI is **mixed, overall red** for this SHA:

| Workflow | Run | Result | Relevant detail |
| --- | ---: | --- | --- |
| RC-1 Gate | `29389871238` | success | all blocking RC-1 jobs passed |
| authority-gates | `29389871224` | success | architecture authority gates passed |
| phase9-cross-platform | `29389871215` | **failure** | Runtime matrices passed; unrelated release/product jobs failed |

Observed Phase 9 failures:

- deterministic Studio E2E stopped at build: Rollup could not resolve `@actalk/inkos-core/interactive-film/evaluator` from `StoryPlayer.tsx`;
- security job found `setuptools 79.0.1 / PYSEC-2026-3447`, fixed in `83.0.0`;
- Windows InkOS suite failed parsing `tui-rc1-interaction.test.tsx` at a dynamic `import(...)`; Ubuntu/macOS InkOS jobs passed.

The Runtime jobs for Windows/Ubuntu/macOS on Python 3.11/3.13 passed in that Phase 9 run. Therefore current CI does not invalidate the Runtime audit evidence, but the repository as a whole cannot be described as green.

## 4. Tests and temporary fixtures executed

All generated databases were under `%TEMP%`; no repository database or source was changed.

| Check | Result |
| --- | --- |
| Runtime full suite | **113 collected, 113 passed**, 34.2 s; cache provider disabled and external `basetemp` used |
| at-revision fixture | revisions 1/2/3 created with different entity location/resource/relationship plus actual relationship and fact events |
| replay fixture | latest, target revision, repeated replay, empty/tampered projections, shuffled ordinal, duplicate logical event, unknown event/schema |
| migration fixture | project revision 7 with current rows, two events lacking `applied_revision`, zero chapter commits |
| exact requested scale | 600 chapters, 10,000 events, 20,002 facts, 2,000 relationships, 500 threads |

These fixtures are diagnostic evidence only. They do not add product tests or functionality.

## 5. Baseline gate

RC-2A baseline is valid. The audit can proceed despite the dirty worktree because the dirt is isolated documentation. RC-2B must not treat those untracked files, passing current projection replay tests, the presence of `story_events`, or the RC-1 closeout as proof of historical reconstruction.
