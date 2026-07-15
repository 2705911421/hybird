# RC-1 CI Gate Report

## Workflow contract

正式 workflow：`.github/workflows/rc1-chapter-authority.yml`，显示名 `RC-1 Gate`，触发器为 `push`、`pull_request`、`workflow_call`。

| Blocking check/job | OS | 内容 |
| --- | --- | --- |
| `Cross-platform gate (ubuntu-latest)` | Ubuntu | install、Python/TS architecture、Runtime full、pip/compile、typecheck、build |
| `Cross-platform gate (windows-latest)` | Windows | 同上 |
| `Cross-platform gate (macos-latest)` | macOS | 同上 |
| `Specialized authority suites` | Ubuntu | Runtime reads/export、Core、Writer A-F、CLI、TUI、Studio API 与三套 full tests |
| `Chromium UI black-box` | Ubuntu | Playwright RC-1 A-F + fault matrix |
| `RC-1 Required Gate` | Ubuntu | `if: always()` 聚合检查，只有前三组全部 success 才通过 |

所有关键 job 都是 blocking；workflow 中没有 `continue-on-error`。fixture、项目数据和 Runtime stub 均来自提交文件，不依赖开发机状态，不调用真实 LLM。

## Release dependency

`.github/workflows/release.yml` 的 `rc1-gate` 使用同一 reusable workflow。`runtime-bundles` 和 `source-and-legal` 均声明 `needs: rc1-gate`，因此 RC-1 gate 未成功时不会生成 release artifacts。

## Branch protection truth

2026-07-15 查询 GitHub API：`master` 返回 `404 Branch not protected`。因此当前不能宣称默认分支已受保护。

仓库管理员必须执行：

1. Settings → Branches → Add branch protection rule，pattern `master`。
2. 启用 “Require status checks to pass before merging”。
3. 将 `RC-1 Required Gate` 设为 required；该 aggregate 已强制依赖全部 OS、specialized 与 Chromium jobs。
4. 启用 “Require branches to be up to date before merging”。
5. 禁止绕过或按仓库策略限制 bypass actors，并保存规则。
6. 用一个 PR 验证 required context 名称与 Actions 实际 check-run 完全一致。

如果管理员希望逐项可见，也可额外 require 上表五个非 aggregate check；最低不可省略的是 `RC-1 Required Gate`。

## Evidence state

| Evidence | 状态 |
| --- | --- |
| YAML parse | PASS |
| local preflight | PASS（不作为最终 release 证据） |
| clean-commit local regression | PASS：`b95298f36c44f447ce5a5d7d10c46d97e8767935`，全部 full/targeted/build gates exit 0 |
| default-branch `RC-1 Required Gate` actual run | PENDING |
| branch protection | NOT ENABLED；需管理员操作 |

因此当前 F-002 为 **PARTIAL**。只有默认分支最终提交的实际 run 成功后，workflow/release 部分才能标记 CLOSED；branch protection 状态仍必须如实保留为管理员待办。

## First default-branch attempt and correction

Run [`29388494342`](https://github.com/2705911421/hybird/actions/runs/29388494342) 证明 blocking 行为生效：Ubuntu `Story Runtime full suite` 因 Phase 7 long-path fixture 的单个 UTF-8 component 超过 Linux 255-byte 限制而失败，aggregate `RC-1 Required Gate` 同步失败。macOS job 已成功；失败不是 `continue-on-error` 或非阻断告警。

提交 `204461a3c0f58e36730d9b33b635698cf1bf023f` 保留长路径覆盖，将一个 270-byte component 改为 30 层 9-byte CJK components，并新增跨平台 component-length 断言。clean commit 本地定点 2/2、Runtime 113/113 与 Python package/architecture gates 通过。后续 default-branch run 才能作为 F-002 的成功证据。

Run [`29388771345`](https://github.com/2705911421/hybird/actions/runs/29388771345) 的 Windows、Ubuntu、macOS jobs 全绿，但 Chromium fresh checkout 在启动 Vite 前没有 Core build artifact，无法解析 Core export，aggregate 继续失败。提交 `6df3c5e02931ba51f7970914a7d8ee61604fdaed` 把 `pnpm --filter @actalk/inkos-core build` 设为 `test:e2e:rc1` 的 lifecycle precondition，并让 workflow 直接运行该固定 Chromium script。clean commit CI 等价命令 13/13 passed（114.48s）；仍需后续 default-branch run 终态 success。

Run [`29389202699`](https://github.com/2705911421/hybird/actions/runs/29389202699) 中三 OS 与 specialized suites 均成功；Chromium 为 12/13，唯一失败是 timeout fault 恢复阶段的悬挂 fixture socket。提交 `d3f55fd290b7ff61abd554c19b4434785a9c0a70` 保留 300ms 产品 timeout/fail-closed 判据，让故意迟到的 fixture response 在 750ms 后结束，并在 Retry 前轮询 Runtime health。clean commit 上 Chromium 13/13 与 TUI 13/13 通过（组合 140.66s）。仍需新的 default-branch aggregate success。
