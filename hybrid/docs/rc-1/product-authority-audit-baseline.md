# RC-1A 产品事实源审计基线

审计日期：2026-07-13（Asia/Shanghai）

## 结论性基线

本审计基于 **dirty snapshot**，不是 clean commit。审计期间未清理、回退或改写任何既有变更；除 `hybrid/docs/rc-1/` 下本次报告外，不应把其他未提交文件归因于 RC-1A。

| 项目 | 值 |
|---|---|
| 根仓库 | `2705911421/hybird` 工作区 `C:\Users\27059\Documents\hybrid-workspace` |
| 根 branch | `master` |
| 根 commit | `d727dd4cd0589bdb856046e92994fa8a5141ef46` |
| InkOS 内嵌仓库 branch | `master` |
| InkOS 内嵌仓库 commit | `fd87b04c3fbac7ab6ebc1b022fa117ee8051825e` |
| InkOS version | `1.7.0`（根 `package.json`） |
| Story Runtime version | `0.1.0` |
| API contract / schema string | `story-runtime/v1` |
| API prefix | `/api/story-runtime/v1` |
| SQLite migration version | `7` |
| OS | Microsoft Windows 11 Home China `10.0.26200`, 64-bit |
| Node | `v24.16.0` |
| pnpm | `9.12.0` |
| Python | `3.11.15` |

版本来源：`inkos/package.json`、`story_runtime/__init__.py`、`api.py:40`、`migrations.py` 的 `MIGRATIONS` 最大版本。Node 版本高于 InkOS 文档推荐的 Node 22，但本次只读测试通过，未观察到由此造成的审计失真。

## Feature flags 与运行配置默认值

审计 shell 中未设置任何 `STORY_RUNTIME_*` 环境变量，因此以下均为当前代码默认值：

| Flag / config | 默认值 | 证据 |
|---|---:|---|
| `STORY_RUNTIME_ENABLE_WRITES` | `0` | `story-runtime/src/story_runtime/config.py:35` |
| `STORY_RUNTIME_UNIFIED_REVIEW_ENABLED` | `0` | `config.py:38` |
| `STORY_RUNTIME_OBSERVABILITY_ENABLED` | `1` | `config.py:39` |
| `STORY_RUNTIME_RECOVERY_ENABLED` | `1` | `config.py:40` |
| `STORY_RUNTIME_MIGRATION_ENABLED` | `1` | `config.py:41` |
| `storyRuntime.mode` | `story-runtime` | `inkos/packages/core/src/story-runtime/schemas.ts:16` |
| `storyRuntime.fallbackOnUnavailable` | `false` | `schemas.ts:15` |
| `INKOS_STUDIO_RUNTIME_PANEL` | enabled unless `0` | `studio/src/api/server.ts:2360` |
| `INKOS_STUDIO_RUNTIME_RECOVERY` | enabled unless `0` | `server.ts:2361` |

重要限制：`fallbackOnUnavailable=false` 并不能保护仍直接调用 `StateManager` 的产品入口；这些入口根本没有进入 Runtime adapter，所以会继续静默读取本地文件。

## 根仓库未提交状态

根仓库 `git status --short --branch` 为 `master...origin/master`，工作区不干净。以下是审计开始时根仓库看到的全部 tracked 修改：

```text
M hybrid/README.md
M hybrid/story-runtime/UPSTREAM_PROVENANCE.yml
M hybrid/story-runtime/pyproject.toml
M hybrid/story-runtime/scripts/benchmark.py
M hybrid/story-runtime/src/story_runtime/__main__.py
M hybrid/story-runtime/src/story_runtime/api.py
M hybrid/story-runtime/src/story_runtime/cli.py
M hybrid/story-runtime/src/story_runtime/config.py
M hybrid/story-runtime/src/story_runtime/database.py
M hybrid/story-runtime/src/story_runtime/migrations.py
M hybrid/story-runtime/src/story_runtime/repository.py
M hybrid/story-runtime/src/story_runtime/services.py
M hybrid/story-runtime/tests/integration/test_cli.py
M hybrid/story-runtime/tests/migration/test_migrations.py
M inkos/packages/core/src/story-runtime/process-manager.ts
M inkos/packages/studio/src/components/Sidebar.tsx
M inkos/packages/studio/src/hooks/use-runtime-polling.ts
```

根仓库看到的全部 untracked 路径（目录代表其下全部文件）为：

```text
.github/workflows/phase9-ci.yml
.github/workflows/phase9-soak.yml
.github/workflows/release.yml
hybrid/NOTICE
hybrid/docs/backup-restore.md
hybrid/docs/capacity-limits.md
hybrid/docs/final-audit/FINAL-AUDIT-REPORT.md
hybrid/docs/final-audit/agent-security-audit.md
hybrid/docs/final-audit/architecture-audit.md
hybrid/docs/final-audit/ci-audit.md
hybrid/docs/final-audit/code-quality-audit.md
hybrid/docs/final-audit/commit-integrity-audit.md
hybrid/docs/final-audit/context-memory-audit.md
hybrid/docs/final-audit/environment-baseline.md
hybrid/docs/final-audit/event-projection-audit.md
hybrid/docs/final-audit/evidence/commands.md
hybrid/docs/final-audit/evidence/package-smoke-runtime.stderr.log
hybrid/docs/final-audit/evidence/package-smoke-runtime.stdout.log
hybrid/docs/final-audit/evidence/performance-million-windows.json
hybrid/docs/final-audit/evidence/soak-windows-0.02h.json
hybrid/docs/final-audit/evidence/studio-runtime.stderr.log
hybrid/docs/final-audit/evidence/studio-runtime.stdout.log
hybrid/docs/final-audit/evidence/studio-server.stderr.log
hybrid/docs/final-audit/evidence/studio-server.stdout.log
hybrid/docs/final-audit/final-scorecard.md
hybrid/docs/final-audit/frankenstein-risk-audit.md
hybrid/docs/final-audit/legacy-removal-audit.md
hybrid/docs/final-audit/migration-audit.md
hybrid/docs/final-audit/performance-audit.md
hybrid/docs/final-audit/product-surface-audit.md
hybrid/docs/final-audit/release-audit.md
hybrid/docs/final-audit/reliability-audit.md
hybrid/docs/final-audit/review-revision-audit.md
hybrid/docs/operations-runbook.md
hybrid/docs/performance-report.md
hybrid/docs/phase-9-benchmark-windows.json
hybrid/docs/phase-9-implementation.md
hybrid/docs/phase-9-known-issues.md
hybrid/docs/phase-9-release-notes.md
hybrid/docs/phase-9-release-scope.md
hybrid/docs/phase-9-studio-benchmark-windows.json
hybrid/docs/phase-9-test-report.md
hybrid/docs/release-checklist.md
hybrid/docs/runtime-packaging.md
hybrid/docs/security-review.md
hybrid/docs/upgrade-compatibility.md
hybrid/docs/upstream-sync.md
hybrid/story-runtime/scripts/generate_synthetic_corpus.py
hybrid/story-runtime/scripts/soak.py
hybrid/story-runtime/src/story_runtime/operations.py
hybrid/story-runtime/src/story_runtime/runtime_logging.py
hybrid/story-runtime/story-runtime.spec
hybrid/story-runtime/tests/integration/test_phase9_stability.py
hybrid/story-runtime/tests/unit/test_synthetic_corpus.py
inkos/packages/core/src/__tests__/story-runtime-process-manager.test.ts
inkos/scripts/studio-e2e-benchmark.mjs
output/playwright/final-audit/runtime-overview-revision-7.png
output/playwright/final-audit/studio-home-zero-chapters.png
```

## InkOS 内嵌仓库未提交状态

InkOS 自身也是 dirty snapshot。其未提交变更覆盖 Phase 8/Runtime authority 主路径，直接影响本审计，因此本报告描述的是这些未提交改动组成的当前产品快照，而不是单独的 `fd87b04...` clean commit。

Tracked 修改/删除：

```text
M package.json
M packages/cli/src/__tests__/cli-integration.test.ts
M packages/cli/src/__tests__/publish-package.test.ts
M packages/cli/src/__tests__/runtime-requirements.test.ts
M packages/cli/src/commands/book.ts
M packages/cli/src/commands/compose.ts
M packages/cli/src/commands/config.ts
M packages/cli/src/commands/doctor.ts
M packages/cli/src/commands/review.ts
M packages/cli/src/commands/status.ts
M packages/cli/src/project-bootstrap.ts
M packages/cli/src/runtime-requirements.ts
M packages/cli/src/tui/app.ts
M packages/cli/src/utils.ts
D packages/core/src/__tests__/agent-import-chapters-tool.test.ts
M packages/core/src/__tests__/agent-session.test.ts
M packages/core/src/__tests__/agent-system-prompt.test.ts
M packages/core/src/__tests__/agent-tools-en-language.test.ts
M packages/core/src/__tests__/agent-tools.test.ts
D packages/core/src/__tests__/chapter-persistence.test.ts
D packages/core/src/__tests__/composer.test.ts
M packages/core/src/__tests__/continuity.test.ts
D packages/core/src/__tests__/hook-arbiter.test.ts
M packages/core/src/__tests__/index-notify-lazy.test.ts
M packages/core/src/__tests__/instruction-adherence-boundary.test.ts
M packages/core/src/__tests__/interaction-tools.test.ts
M packages/core/src/__tests__/memory-retrieval.test.ts
D packages/core/src/__tests__/pipeline-runner-memory-sync.test.ts
D packages/core/src/__tests__/pipeline-runner.test.ts
D packages/core/src/__tests__/revise-foundation.test.ts
M packages/core/src/__tests__/runtime-state-store.test.ts
D packages/core/src/__tests__/spinoff-foundation-context.test.ts
M packages/core/src/__tests__/state-manager.test.ts
M packages/core/src/__tests__/writer.test.ts
M packages/core/src/agent/agent-session.ts
M packages/core/src/agent/agent-system-prompt.ts
M packages/core/src/agent/agent-tools.ts
D packages/core/src/agent/chapter-import-source.ts
M packages/core/src/agent/index.ts
M packages/core/src/agents/architect.ts
M packages/core/src/agents/composer.ts
M packages/core/src/agents/continuity.ts
M packages/core/src/agents/writer.ts
M packages/core/src/index.ts
M packages/core/src/interaction/project-tools.ts
M packages/core/src/models/book.ts
M packages/core/src/models/input-governance.ts
M packages/core/src/models/project.ts
D packages/core/src/pipeline/chapter-persistence.ts
M packages/core/src/pipeline/chapter-review-cycle.ts
M packages/core/src/pipeline/runner.ts
M packages/core/src/state/manager.ts
M packages/core/src/state/runtime-state-store.ts
D packages/core/src/state/state-bootstrap.ts
M packages/core/src/utils/context-assembly.ts
D packages/core/src/utils/hook-arbiter.ts
M packages/core/src/utils/memory-retrieval.ts
M packages/studio/src/App.tsx
M packages/studio/src/api/phase5-hotfix.test.ts
M packages/studio/src/api/server.test.ts
M packages/studio/src/api/server.ts
M packages/studio/src/api/v13-hotfix-round4.test.ts
M packages/studio/src/components/Sidebar.tsx
M packages/studio/src/hooks/use-hash-route.ts
M packages/studio/src/hooks/use-i18n.ts
M packages/studio/src/pages/BookDetail.tsx
M packages/studio/src/pages/ChapterReader.tsx
```

Untracked：

```text
packages/core/src/__tests__/chapter-persistence-port.test.ts
packages/core/src/__tests__/composer-runtime-authority.test.ts
packages/core/src/__tests__/phase8-foundation-readonly.test.ts
packages/core/src/__tests__/review-artifacts.test.ts
packages/core/src/__tests__/story-runtime-integration.test.ts
packages/core/src/__tests__/story-runtime-process-manager.test.ts
packages/core/src/__tests__/story-runtime-process-windows.test.ts
packages/core/src/pipeline/chapter-persistence-port.ts
packages/core/src/review-artifacts/adapters.ts
packages/core/src/review-artifacts/schemas.ts
packages/core/src/review-artifacts/untrusted-parser.ts
packages/core/src/state/durable-story-progress.ts
packages/core/src/story-runtime/client.ts
packages/core/src/story-runtime/context-provider.ts
packages/core/src/story-runtime/process-manager.ts
packages/core/src/story-runtime/schemas.ts
packages/studio/.phase6-studio.err.log
packages/studio/.phase6-studio.out.log
packages/studio/src/__tests__/legacy-migration-proxy.test.ts
packages/studio/src/__tests__/runtime-observability-proxy.test.ts
packages/studio/src/__tests__/story-runtime-status-endpoint.test.ts
packages/studio/src/hooks/use-runtime-polling.ts
packages/studio/src/pages/LegacyMigrationWizard.tsx
packages/studio/src/pages/RuntimePanel.tsx
scripts/migrate-phase8-config.mjs
scripts/studio-e2e-benchmark.mjs
```

## Dirty snapshot 对审计的影响

- **直接影响**：Runtime API、DB migration、repository/service、InkOS Runtime client/process manager、Studio server、pipeline、StateManager 及 CLI status 均在变更集中。审计结论只对该 snapshot 有效。
- **不改变核心判断**：实际调用链和 fixture 均从当前文件与当前运行结果取得；没有借用 clean commit 的假设。
- **潜在重现风险**：若只 checkout 两个 SHA，许多 Runtime authority 文件将消失或不同，不能声称可从 clean SHA 单独重现本报告。
- **审计产物隔离**：本任务只新增 `hybrid/docs/rc-1/*.md`。未修改业务代码、schema、测试或真实项目数据。

## 已执行只读验证

| 套件 | 结果 |
|---|---:|
| Story Runtime pytest | `107 passed` |
| InkOS Core targeted tests | `60 passed` |
| Studio targeted tests | `136 passed` |
| CLI/TUI targeted tests | `25 passed` |

这些通过结果验证当前实现内部自洽，但没有覆盖 Runtime authority 的 A-E 产品一致性矩阵，不能作为单一事实源已经完成的证据。
