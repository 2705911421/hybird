# 最终审计环境基线

审计日期：2026-07-13（Asia/Shanghai）  
审计对象：当前工作区快照，不是纯净 commit。

## 版本与环境

| 项目 | 事实 | 状态 | 证据 |
|---|---|---|---|
| Commit | `d727dd4cd0589bdb856046e92994fa8a5141ef46` | PASS | `git rev-parse HEAD` |
| Branch | `master`，跟踪 `origin/master` | PASS | `git status --branch --short` |
| Tag | HEAD 无 tag；`d727dd4-dirty` | PASS | `git describe --tags --always --dirty` |
| InkOS | `1.7.0` | PASS | `inkos/package.json` |
| Story Runtime | `0.1.0` | PASS | `hybrid/story-runtime/pyproject.toml` |
| API contract | `story-runtime/v1` | PASS | `hybrid/contracts/story-runtime.openapi.yaml`、`api.py:41` |
| DB schema | migration `7` | PASS | `migrations.py`；全量 Python 测试 |
| Node | `v24.16.0` | PASS | `node --version` |
| pnpm | `9.12.0` | PASS | `pnpm --version` |
| Python | `3.11.15` | PASS | `python --version` |
| SQLite | `3.53.1` | PASS | 百万字 benchmark 环境记录 |
| OS | Windows 11 Home China x64，`10.0.26200` | PASS | PowerShell/benchmark platform |
| macOS/Linux | 未在本机执行 | NOT VERIFIED | 缺少对应 clean host/VM |

DB migrations：`authority_core`、`deterministic_retrieval`、`chapter_commit_authority`、`unified_review_artifacts`、`studio_observability`、`legacy_project_import`、`phase9_scale_indexes`。

## 仓库入口事实

| 入口 | 实际位置 | 状态 |
|---|---|---|
| CLI | `inkos/packages/cli/src/index.ts` | PASS |
| Studio | `inkos/packages/studio/src/api/server.ts`、React client | PASS |
| TUI | `inkos/packages/cli/src/tui/app.ts` | PASS |
| Core pipeline | `inkos/packages/core/src/pipeline/runner.ts` | PASS |
| Story Runtime | `hybrid/story-runtime/src/story_runtime/__main__.py`、`api.py` | PASS |
| Installer/launcher | Runtime PyInstaller spec 存在；产品 sidecar 未接线 | PARTIAL |
| Migration | `migration_jobs.py`、Studio migration proxy | PASS（功能存在） |
| Benchmark/soak | `benchmark.py`、`soak.py` | PASS（当前工作区未跟踪部分） |
| CI | HEAD 仅跟踪 `.github/workflows/ci.yml` | FAIL |
| Release | `.github/workflows/release.yml` 未跟踪 | FAIL |

## 初始工作区状态

审计开始前工作区不干净：17 个已修改文件，以及大量未跟踪 Phase 9、release、test 和 docs 文件。已修改文件包括：

`hybrid/README.md`、`hybrid/story-runtime/UPSTREAM_PROVENANCE.yml`、`pyproject.toml`、`scripts/benchmark.py`、`__main__.py`、`api.py`、`cli.py`、`config.py`、`database.py`、`migrations.py`、`repository.py`、`services.py`、`tests/integration/test_cli.py`、`tests/migration/test_migrations.py`、`inkos/.../process-manager.ts`、`Sidebar.tsx`、`use-runtime-polling.ts`。

未跟踪内容包含三个新 workflow、Phase 9 implementation/tests/scripts、release/legal/operations 文档和本次 `final-audit` 输出。完整列表以审计结束时 `git status --short` 为准。

结论：`FAIL`（发布基线不可复现）。当前测试结果包含未提交实现，远端 HEAD 的 CI 不能证明这份快照。

## 审计影响判断

- 未覆盖、未回退用户变更；审计只新增报告和生成型证据。
- 脏工作区直接影响 Runtime、schema、benchmark、process manager、Studio UI 与 CI 结论，属于实质影响。
- 本报告不能作为 `d727dd4` 的 release attestation，也不能证明任一未跟踪 workflow 已运行。

