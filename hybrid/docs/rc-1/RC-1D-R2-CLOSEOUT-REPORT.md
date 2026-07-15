# RC-1D-R2 Closeout Report

日期：2026-07-15
范围：F-002、F-003、F-004 与 RC-1 最终收口；未开始 RC-2。

## 当前判定

| Finding | 状态 | 判据 |
| --- | --- | --- |
| F-001 | CLOSED | Runtime-authority Writer recent narrative、正文集合与 revision 均来自 Runtime；A-F red-team 与 architecture gate 保持通过。 |
| F-002 | PARTIAL | 正式三 OS blocking workflow 与 release 依赖已提交；clean commit 本地全回归通过，仍须默认分支实际 run 成功后关闭。 |
| F-003 | CLOSED | Studio Chromium 13 个浏览器黑盒场景和 TUI 13 个交互场景覆盖 A-F、七类 fault 与恢复，无 local fallback。 |
| F-004 | CLOSED | Runtime/legacy/importer mode-specific prompt 已修正并由 36 个 prompt 测试覆盖。 |

在默认分支的 `RC-1 Required Gate` 对最终提交实际成功前，整体结论保持：**RC-1D REMAINS BLOCKED**。

## F-004 关闭证据

Runtime authority system prompt 明确规定：章节集合、顺序、正文、摘要、最近叙事和 revision 只能来自 Story Runtime capability；Agent 不得用 file/read/grep/list 工具读取 `chapters/index.json` 或章节 Markdown 绕过 Runtime。local index/Markdown 只被描述为 legacy、显式 importer 输入或 export projection，且不是当前 authority。prompt 不暴露 Runtime DB 路径、表名或内部文件。

Legacy mode 保留了明确限于 legacy 项目的本地读取说明；importer mode 可描述 source files，但明确它们只是导入输入。Runtime fault 必须停止当前操作，不能切换到本地 owner。

## F-003 关闭证据

可提交 fixture orchestrator 固定 `project=rc1-ui-verification`、`revision=7`、Runtime chapters `1..3`、`latest=3`，并独立生成 A-F 六种本地状态。Studio 与 TUI 都由真实交互驱动，不是 formatter/helper 单测。

每种本地状态都验证 count/latest/revision 为 `3/3/7`、chapter 2 body/hash 来自 Runtime、chapter 4 与 local latest 99 不出现、analytics/search/export 使用 Runtime，且缺少 projection 不失败。connection refused、timeout、degraded、malformed DTO、version mismatch、authorization、DB locked 均显示明确错误，隐藏旧本地数据，阻止 export/write，并能在 Runtime 恢复后 retry。

详细矩阵见 `RC-1-UI-BLACKBOX-MATRIX.md`。

## F-002 实现与剩余外部验证

`.github/workflows/rc1-chapter-authority.yml` 现在是可复用的 `RC-1 Gate`，在 push、pull_request、workflow_call 上运行 Windows/Ubuntu/macOS，并包含 blocking aggregate `RC-1 Required Gate`。关键 jobs 均无 `continue-on-error`。`.github/workflows/release.yml` 先调用该 workflow，所有 release artifact jobs 都 `needs: rc1-gate`。

仓库当前 `master` branch protection API 返回 404（未保护）。代码不能替管理员启用 protection，因此不能宣称已经保护；管理员操作见 `RC-1-CI-GATE-REPORT.md`。这不改变 workflow 本身的 blocking 依赖，但合并保护仍需仓库管理员执行。

## Clean-commit 回归证据

实现提交：`b95298f36c44f447ce5a5d7d10c46d97e8767935`。运行前后 `git status --short` 均为空；Playwright 生成的 `output/rc1-ui` 已删除。所有下表成功结果均直接来自该 clean commit，不使用 dirty-worktree 预检作为证据。

| Gate / command | Exit | Tests / checks | 实测耗时 |
| --- | ---: | --- | ---: |
| `python -m pytest -q` | 0 | Runtime 113 passed | 34.44s |
| `pnpm --filter @actalk/inkos-core test` | 0 | 173 files / 1572 passed | 53.39s |
| `pnpm --filter @actalk/inkos test` | 0 | 40 files / 219 passed | 167.50s |
| `pnpm --filter @actalk/inkos-studio test` | 0 | 58 files / 503 passed | 75.10s |
| `pnpm exec playwright test --config playwright.rc1.config.ts --project=chromium --reporter=line` | 0 | Chromium 13 passed | 134.35s |
| `python hybrid/scripts/check_architecture.py` + `pip check` + `compileall` | 0 | 10 authority rules；no broken requirements | 4.23s |
| `pnpm check:chapter-authority` | 0 | 439 modules / 319 edges / 24022 call sites | 3.03s |
| `pnpm typecheck` | 0 | Core + Studio + CLI | 58.69s |
| `pnpm build` | 0 | Core + Studio client/server + CLI | 73.52s |
| Runtime chapter read/export targeted | 0 | 5 passed | 2.05s |
| Core authority/Writer/prompt targeted | 0 | 7 files / 128 passed | 10.30s |
| CLI A-F/API matrix targeted | 0 | 2 files / 49 passed | 138.42s |
| Interactive TUI matrix targeted | 0 | 2 files / 14 passed | 34.85s |
| Studio API/fail-closed targeted | 0 | 2 files / 136 passed | 13.09s |

首次 architecture 组合调用在错误工作目录下立即以 exit 2 报路径不存在，未运行测试；修正 cwd 后上表正式命令 exit 0。该操作错误不被计作通过证据，也未改变工作树。

- clean implementation commit：`b95298f36c44f447ce5a5d7d10c46d97e8767935`
- clean-commit local gate：`PASS`
- default-branch GitHub Actions run：`PENDING`
- final closeout commit：`PENDING`

## 默认分支 CI 修复记录

默认分支 run [`29388494342`](https://github.com/2705911421/hybird/actions/runs/29388494342) 正确被 aggregate 阻断：macOS 全绿，Ubuntu 的 Runtime full suite 有 2 个 Phase 7 fixture 测试因单个 CJK path component 为 270 UTF-8 bytes、超过 Linux `NAME_MAX=255` 而失败，`RC-1 Required Gate` 随之失败。没有忽略或重跑掩盖该结果。

修复提交 `204461a3c0f58e36730d9b33b635698cf1bf023f` 将同样的 30 段 CJK long-path 语义改为 30 层短 component，并新增每个 component 不超过 255 bytes 的断言。该 clean commit 上定点 2/2、Runtime full 113/113、architecture、pip check 与 compileall 均 exit 0。下一次默认分支 run 尚待实际成功。

第二次默认分支 run [`29388771345`](https://github.com/2705911421/hybird/actions/runs/29388771345) 中 Windows、Ubuntu、macOS cross-platform jobs 已全部成功，证明路径修复有效；Chromium job 则在 fresh checkout 启动 Vite 时发现 Core `dist` 尚未构建，aggregate 再次正确失败。提交 `6df3c5e02931ba51f7970914a7d8ee61604fdaed` 为 `test:e2e:rc1` 增加显式 Core prebuild，并删除 workflow 的冗余 Playwright 参数。该 clean commit 上 CI 等价 package script 13/13 passed，exit 0，114.48s。下一次默认分支 run 仍须实际成功。

第三次默认分支 run [`29389202699`](https://github.com/2705911421/hybird/actions/runs/29389202699) 的三 OS 与 specialized jobs 全绿；Chromium 12/13，timeout fault 恢复时 fixture 的永不结束 response 污染 CI HTTP 连接，10s 内没有呈现恢复数据，aggregate 再次失败。提交 `d3f55fd290b7ff61abd554c19b4434785a9c0a70` 仍让客户端在 300ms fail closed，但在 750ms 后结束迟到 fixture response，并在 UI Retry 前确认 Runtime health 恢复。该 clean commit 完整 Chromium 13/13 与 TUI 13/13 通过，组合 exit 0，140.66s。后续默认分支 run 仍须 actual success。

## 禁止项核对

未修改历史 Runtime event/revision，未重写 Studio，未修改章节事务，未新增 authority mode，未恢复 shadow writing，未降低 Runtime unavailable fail-closed 标准，未开始 RC-2。

## 最终放行条件

只有 clean commit 完整回归通过、工作区 clean、最终提交已推送且默认分支 `RC-1 Required Gate` 实际成功，F-002 才可改为 CLOSED，并输出 `RC-1D COMPLETE / READY FOR RC-1 FINAL GATE`。否则保持 `RC-1D REMAINS BLOCKED`。
